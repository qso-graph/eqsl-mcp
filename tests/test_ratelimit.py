"""The server spaces its requests to eQSL.cc.

Asserting it because a convention nobody asserts drifts -- which is how
get_version_info drifted across this fleet.
"""

from __future__ import annotations

import time

import pytest

from eqsl_mcp import ratelimit


@pytest.fixture(autouse=True)
def _clean() -> None:
    """This module holds process-wide state, so each test starts from none.

    Without it a 429 armed by one test blocks the spacing tests, and the order
    they run in decides whether the suite passes.
    """
    ratelimit.clear()


def test_min_interval_is_declared_and_positive():
    assert ratelimit.MIN_INTERVAL > 0


def test_consecutive_calls_are_spaced():
    ratelimit.wait()                      # establish the baseline
    start = time.monotonic()
    ratelimit.wait()
    elapsed = time.monotonic() - start
    # Allow a little slack for a slow scheduler, but it must actually wait.
    assert elapsed >= ratelimit.MIN_INTERVAL * 0.8, (
        f"second call returned after {elapsed:.3f}s, "
        f"MIN_INTERVAL is {ratelimit.MIN_INTERVAL}"
    )


def test_a_gap_longer_than_the_interval_is_not_padded():
    ratelimit.wait()
    time.sleep(ratelimit.MIN_INTERVAL * 1.2)
    start = time.monotonic()
    ratelimit.wait()
    # Nothing to wait for: the gap already passed.
    assert time.monotonic() - start < ratelimit.MIN_INTERVAL * 0.5


# --- what a 429 does -------------------------------------------------------
#
# Separate from spacing above, deliberately: a gap between requests and an
# interval eQSL asked us to wait are different mechanisms, and reading
# one as the other is what this module's comments exist to prevent.


def test_backoff_bounds_are_declared():
    assert 0 < ratelimit.MIN_BACKOFF < ratelimit.MAX_BACKOFF


@pytest.mark.parametrize(
    "header,expected",
    [
        (None, ratelimit.MIN_BACKOFF),      # absent: wait the floor, do not guess
        ("", ratelimit.MIN_BACKOFF),
        ("0", ratelimit.MIN_BACKOFF),       # "now" still gets a floor
        ("5", ratelimit.MIN_BACKOFF),       # below the floor is raised to it
        ("300", 300.0),                     # honoured as stated
        ("99999", ratelimit.MAX_BACKOFF),   # above the ceiling is capped
        ("Wed, 21 Oct 2026 07:28:00 GMT", ratelimit.MIN_BACKOFF),  # date unparsed
        ("garbage", ratelimit.MIN_BACKOFF),
    ],
)
def test_retry_after_is_honoured_within_bounds(header, expected):
    assert ratelimit.retry_after(header) == expected


def test_a_block_refuses_the_next_request_without_sleeping():
    """The contract: refuse quickly and say when, never sleep out the wait."""
    waited = ratelimit.block("300")
    assert waited == 300.0
    start = time.monotonic()
    with pytest.raises(ratelimit.RateLimited) as e:
        ratelimit.wait()
    assert time.monotonic() - start < 1.0, "wait() slept through the backoff"
    assert e.value.retry_after <= 300
    assert "300" in str(e.value) or str(e.value.retry_after) in str(e.value)


def test_the_block_covers_every_caller():
    """A limit is eQSL's view of this client, not of one endpoint."""
    ratelimit.block("120")
    for _ in range(3):
        with pytest.raises(ratelimit.RateLimited):
            ratelimit.wait()


def test_clearing_the_block_lets_requests_resume():
    ratelimit.block("120")
    with pytest.raises(ratelimit.RateLimited):
        ratelimit.wait()
    ratelimit.clear()
    ratelimit.wait()  # must not raise


def test_rate_limited_is_a_runtime_error():
    """Callers already handling this client's failures keep working, and
    FastMCP flags the tool result isError either way."""
    assert issubclass(ratelimit.RateLimited, RuntimeError)


# --- the wiring ------------------------------------------------------------
#
# The module above is only useful if the fetch paths actually consult it. eQSL
# has two, in client.py and ag_cache.py, and they share the block: a limit is
# eQSL's view of this client, not of one URL.


def _http_error(code: int, **headers: str):
    import urllib.error
    from email.message import Message

    m = Message()
    for k, v in headers.items():
        m[k.replace("_", "-")] = v
    return urllib.error.HTTPError(
        "https://www.eqsl.cc/qslcard/DownloadInBox.cfm", code, "nope", m, None
    )


def test_a_429_from_eqsl_arms_the_block(monkeypatch):
    from eqsl_mcp import client as c

    monkeypatch.setattr(
        c.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(429, Retry_After="120")),
    )
    with pytest.raises(ratelimit.RateLimited) as e:
        c._get("https://www.eqsl.cc/qslcard/DownloadInBox.cfm")
    assert e.value.retry_after == 120

    sent: list[str] = []
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda *a, **k: sent.append("x"))
    with pytest.raises(ratelimit.RateLimited):
        c._get("https://www.eqsl.cc/qslcard/DownloadInBox.cfm")
    assert sent == [], "a request was sent while eQSL had told us to stop"


def test_the_ag_list_shares_the_block(monkeypatch):
    """Two fetch paths, one provider: a 429 on either stops both."""
    from eqsl_mcp import ag_cache
    from eqsl_mcp import client as c

    ratelimit.block("120")
    monkeypatch.setattr(
        ag_cache.urllib.request, "urlopen", lambda *a, **k: pytest.fail("sent")
    )
    with pytest.raises(ratelimit.RateLimited):
        ag_cache._download_ag_list()
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda *a, **k: pytest.fail("sent"))
    with pytest.raises(ratelimit.RateLimited):
        c._get("https://www.eqsl.cc/qslcard/DownloadInBox.cfm")


def test_a_429_is_not_reported_as_a_credentials_problem(monkeypatch):
    """The old behaviour: every failure became "check network and
    credentials", so a rate limit read as a wrong password."""
    from eqsl_mcp import client as c

    monkeypatch.setattr(
        c.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(429, Retry_After="90")),
    )
    with pytest.raises(RuntimeError) as e:
        c._get("https://www.eqsl.cc/qslcard/DownloadInBox.cfm")
    assert "credentials" not in str(e.value).lower()
    assert "rate limiting" in str(e.value)


def test_a_500_still_leaks_neither_password_nor_url(monkeypatch):
    from eqsl_mcp import client as c

    monkeypatch.setattr(
        c.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(500)),
    )
    with pytest.raises(RuntimeError) as e:
        c._get(
            "https://www.eqsl.cc/qslcard/DownloadInBox.cfm",
            {"UserName": "KI7MT", "Password": "SECRET"},
        )
    assert "SECRET" not in str(e.value)
    assert "eqsl.cc" not in str(e.value)
