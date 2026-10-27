"""HTTP client layer for eQSL.cc endpoints."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from qso_graph_auth.identity import PersonaManager

from . import __version__, _tls, ratelimit
from .parser import FetchResult, parse_adif, to_mmddyyyy, to_qso, to_yyyymmddhhmm

_BASE = "https://www.eqsl.cc"

# Mock ADIF for testing without credentials
_MOCK_ADIF = (
    "<CALL:5>KI7MT<QSO_DATE:8>20250901<TIME_ON:6>010203<BAND:3>20M<MODE:3>FT8"
    "<EQSL_QSL_RCVD:1>Y<EQSL_QSLRDATE:8>20250902<APP_EQSL_AG:1>Y<EOR>"
    "<CALL:5>K7ABC<QSO_DATE:8>20250901<TIME_ON:6>040506<BAND:3>40M<MODE:2>CW"
    "<EQSL_QSL_RCVD:1>N<EOR>"
)

# Regex to find the .adi download link in the HTML response
_ADI_LINK_RE = re.compile(r'href="([^"]*\.adi)"', re.IGNORECASE)


def _is_mock() -> bool:
    return os.getenv("EQSL_MCP_MOCK") == "1"


def _safe_error(text: str, secret: str | None) -> str:
    """eQSL's own message, or a fixed one when it cannot be shown safely.

    ``last_upload_date`` strips the tags off eQSL's response and returns what is
    left. That body is eQSL's, not ours, and this server's requests put the
    password in the query string — so a page echoing the request puts the
    password into the message. Measured, not assumed: given such a body the
    sentinel came straight through.

    Until #23 that landed in a payload; it is now the error text a client
    reads. So the text is passed on only when it carries neither the secret nor
    anything URL-shaped, and is capped. It is deliberately *not* scrubbed and
    handed over: a body containing the password is a surprise worth reporting
    as one rather than editing quietly.

    Follows lotw-mcp, which has the same shape of hazard for the same reason.
    """
    if secret and secret in text:
        return "eQSL returned a response that echoed the request; not shown"
    if "://" in text:
        return "eQSL returned a response containing a URL; not shown"
    return text[:200]


def _get(url: str, query: dict[str, Any] | None = None,
         timeout: float = 30.0) -> tuple[int, str]:
    """HTTP GET, return (status, text).

    Catches all urllib exceptions to prevent credential-bearing URLs
    from leaking through error messages (eQSL puts passwords in query params).
    """
    if query:
        qs = urllib.parse.urlencode(query, doseq=True)
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, method="GET")
    # Identify this server to eQSL. It sent no User-Agent at all before
    # 2026-10-26, so its requests were indistinguishable from any other script's
    # and eQSL had no way to tell who was asking or ask us to ease off.
    req.add_header("User-Agent", f"eqsl-mcp/{__version__} (+https://qso-graph.io)")
    try:
        ratelimit.wait(url)
        with urllib.request.urlopen(req, timeout=timeout, context=_tls.context()) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # A 429 is eQSL stating its limit outright, so it is honoured. Only the
        # status and Retry-After are read off the exception; its text and .url
        # are not used, because this URL carries the password in its query
        # string -- the same reason the clause below names neither. 503 counts
        # only with Retry-After, which is a deliberate shed; a bare 503 is an
        # outage and falls through.
        if exc.code == 429 or (exc.code == 503 and exc.headers.get("Retry-After")):
            raise ratelimit.RateLimited(
                ratelimit.block(url, exc.headers.get("Retry-After"))
            ) from None
        raise RuntimeError("eQSL request failed — check network and credentials") from None
    except ratelimit.RateLimited:
        # Raised by ratelimit.wait() when a previous 429 is still in force. It
        # must not be rewritten as a credentials problem by the clause below:
        # it is the one failure here that tells the user what to do.
        raise
    except Exception:
        raise RuntimeError("eQSL request failed — check network and credentials") from None


# ---------------------------------------------------------------------------
# eqsl_inbox / eqsl_download
# ---------------------------------------------------------------------------

def _fetch_inbox_adif(
    pm: PersonaManager,
    persona: str,
    since: str | None = None,
    qth_nickname: str | None = None,
) -> str:
    """Fetch raw ADIF text from eQSL inbox.

    Two-step flow: GET DownloadInBox.cfm → parse HTML for .adi link → fetch ADIF.
    Fallback: if the response body contains <EOH> or <EOR>, treat as direct ADIF.
    Returns raw ADIF text string.
    """
    if _is_mock():
        sample = os.getenv("EQSL_MCP_ADIF")
        if sample and os.path.exists(sample):
            return open(sample, encoding="utf-8").read()
        return _MOCK_ADIF

    username, password = pm.require(persona, "eqsl")

    query: dict[str, Any] = {
        "UserName": username,
        "Password": password,
    }
    if since is not None:
        query["RcvdSince"] = to_yyyymmddhhmm(since)
    if qth_nickname:
        query["QTHNickname"] = qth_nickname

    status, body = _get(f"{_BASE}/qslcard/DownloadInBox.cfm", query)
    if status != 200:
        return ""

    # Check if this is already ADIF (some responses come direct)
    upper = body.upper()
    if "<EOH>" in upper or "<EOR>" in upper:
        return body

    # Two-step: extract .adi link from HTML
    m = _ADI_LINK_RE.search(body)
    if not m:
        return ""

    adi_url = m.group(1)
    if not adi_url.startswith("http"):
        adi_url = f"{_BASE}{adi_url}" if adi_url.startswith("/") else f"{_BASE}/{adi_url}"

    _, adif_text = _get(adi_url)
    return adif_text


def download_inbox(
    pm: PersonaManager,
    persona: str,
    since: str | None = None,
    qth_nickname: str | None = None,
) -> FetchResult:
    """Download incoming eQSLs for a persona, parsed into records."""
    adif_text = _fetch_inbox_adif(pm, persona, since=since, qth_nickname=qth_nickname)
    if not adif_text:
        return FetchResult(records=[])
    return FetchResult(records=[to_qso(r) for r in parse_adif(adif_text)])


def download_adif(
    pm: PersonaManager,
    persona: str,
    since: str | None = None,
    qth_nickname: str | None = None,
) -> dict[str, Any]:
    """Download eQSL inbox as raw ADIF text.

    Omit 'since' to download entire inbox history.
    Returns dict with 'adif' (raw text) and 'record_count'.
    """
    adif_text = _fetch_inbox_adif(pm, persona, since=since, qth_nickname=qth_nickname)
    record_count = adif_text.upper().count("<EOR>")
    return {"adif": adif_text, "record_count": record_count}


# ---------------------------------------------------------------------------
# eqsl_verify
# ---------------------------------------------------------------------------

def verify_qso(
    from_call: str,
    to_call: str,
    band: str,
    qso_date: str,
    mode: str | None = None,
) -> dict[str, Any]:
    """Verify a QSO exists in eQSL (public, no auth).

    Args:
        qso_date: YYYY-MM-DD format.
    """
    if _is_mock():
        return {"verified": True, "ag": True, "message": "Result - QSO on file for AG member"}

    query: dict[str, Any] = {
        "CallsignFrom": from_call.upper(),
        "CallsignTo": to_call.upper(),
        "QSOBand": band.upper(),
        "QSODate": to_mmddyyyy(qso_date),
    }
    if mode:
        query["QSOMode"] = mode.upper()

    _, body = _get(f"{_BASE}/qslcard/VerifyQSO.cfm", query)

    text = body.strip()
    verified = "qso on file" in text.lower()
    ag = "ag member" in text.lower()
    return {"verified": verified, "ag": ag, "message": text}


# ---------------------------------------------------------------------------
# eqsl_last_upload
# ---------------------------------------------------------------------------

def last_upload_date(pm: PersonaManager, persona: str) -> dict[str, Any]:
    """Get the last upload date for a persona."""
    if _is_mock():
        return {"persona": persona, "last_upload": "2026-03-01 12:00:00"}

    username, password = pm.require(persona, "eqsl")

    query: dict[str, Any] = {
        "UserName": username,
        "Password": password,
    }
    status, body = _get(f"{_BASE}/qslcard/DisplayLastUploadDate.cfm", query)
    if status != 200:
        raise RuntimeError(f"eQSL returned HTTP {status}")

    # Response is HTML-wrapped — strip tags and extract text content
    text = re.sub(r"<[^>]+>", "", body).strip()
    if not text or "error" in text.lower():
        # Built first and raised second, so the raise interpolates only a value
        # already checked safe to show.
        message = _safe_error(text, password) if text else "Unknown error"
        raise RuntimeError(f"eQSL: {message}")
    return {"persona": persona, "last_upload": text}
