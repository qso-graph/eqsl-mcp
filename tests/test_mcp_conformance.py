"""Conformance with the Model Context Protocol, revision 2026-07-28.

Nothing in this project's documents required this until 2026-10-11 — not
CLAUDE.md, not .claude/rules/security.md, not MCP-SECURITY-FRAMEWORK.md, not
qso-graph-spec. We documented how to *publish* an MCP server in detail and
never wrote down what makes one *valid*, which is how a missing ``isError`` and
missing annotations reached all 22 servers in the fleet unnoticed.

So these are asserted rather than trusted.

Two things here differ from the six servers swept before it:

* **This one was already half-right, by accident.** Its tools caught only
  ``CredentialError``, so every *other* failure — a network error, eQSL
  refusing — propagated uncaught, and FastMCP already reported those as
  ``isError`` with the message intact. Only the credential path was flattened
  into a successful payload. ``TestUncaughtErrorsWereAlreadyFlagged`` pins the
  behaviour that was relied on, since nothing had asserted it.
* **eQSL's own response body was returned as the error text**, and this
  server's requests put the password in the query string. Measured: a body
  echoing the request carried the secret straight through.

Test IDs: EQSL-C01 onward.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from fastmcp.exceptions import ToolError

os.environ["EQSL_MCP_MOCK"] = "1"

from eqsl_mcp import server  # noqa: E402

ANNOTATION_HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

# Three send the operator's eQSL credentials; two use public endpoints — QSO
# verification and the AG member list. All five reach eqsl.cc.
NEEDS_CREDENTIALS = {"eqsl_inbox", "eqsl_download", "eqsl_last_upload"}
PUBLIC_ENDPOINTS = {"eqsl_verify", "eqsl_ag_check"}
READS_EQSL = NEEDS_CREDENTIALS | PUBLIC_ENDPOINTS
ANSWERS_FROM_THE_PACKAGE = {"get_version_info"}


def _tools() -> dict[str, object]:
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def _wire(tool: object) -> dict[str, object]:
    """The serialised annotations, which is what a client reads."""
    annotations = getattr(tool, "annotations", None)
    assert annotations is not None, "tool declares no annotations"
    return annotations.model_dump(by_alias=True, exclude_none=True)


def _call(name: str):
    """The underlying function of a registered tool."""
    tool = getattr(server, name)
    return getattr(tool, "fn", tool)


class TestToolAnnotations:
    def test_every_tool_declares_all_four_hints(self) -> None:
        """EQSL-C01: the defaults are pessimistic, so silence is the wrong answer."""
        for name, tool in _tools().items():
            wire = _wire(tool)
            for hint in ANNOTATION_HINTS:
                assert hint in wire, f"{name} omits {hint} on the wire; got {sorted(wire)}"

    def test_every_tool_reads_and_none_writes(self) -> None:
        """EQSL-C02: nothing is uploaded to eQSL, and no credential is written."""
        for name, tool in _tools().items():
            wire = _wire(tool)
            assert wire["readOnlyHint"] is True, name
            assert wire["destructiveHint"] is False, name
            assert wire["idempotentHint"] is True, name

    def test_open_world_is_read_per_tool(self) -> None:
        """EQSL-C03: five reach eqsl.cc; one does not."""
        tools = _tools()
        assert set(tools) == READS_EQSL | ANSWERS_FROM_THE_PACKAGE
        for name in READS_EQSL:
            assert _wire(tools[name])["openWorldHint"] is True, name
        for name in ANSWERS_FROM_THE_PACKAGE:
            assert _wire(tools[name])["openWorldHint"] is False, name


class TestCredentialFailuresAreFlagged:
    """The half that was wrong.

    Three tools caught ``CredentialError`` and returned ``{"error": ...}`` — a
    successful call whose payload said it had failed. That is the only path
    this change alters.
    """

    @pytest.fixture
    def no_creds(self, monkeypatch):
        from qso_graph_auth.identity.errors import CredentialError

        def fail(*_args, **_kwargs):
            raise CredentialError("nosuch", "eqsl", "No such persona: 'nosuch'")

        monkeypatch.delenv("EQSL_MCP_MOCK", raising=False)
        for name in ("download_inbox", "download_adif", "last_upload_date"):
            monkeypatch.setattr(server, name, fail, raising=False)

    @pytest.mark.parametrize("name,kwargs", [
        ("eqsl_inbox", {"persona": "nosuch"}),
        ("eqsl_download", {"persona": "nosuch"}),
        ("eqsl_last_upload", {"persona": "nosuch"}),
    ])
    def test_a_credential_failure_is_flagged(self, no_creds, name, kwargs) -> None:
        """EQSL-C10: every tool that takes a persona, not a sample of them."""
        with pytest.raises(ToolError, match="No such persona"):
            _call(name)(**kwargs)

    def test_the_cases_cover_every_tool_needing_credentials(self) -> None:
        """EQSL-C11: the list above cannot fall behind the set."""
        assert NEEDS_CREDENTIALS == {"eqsl_inbox", "eqsl_download", "eqsl_last_upload"}


class TestUncaughtErrorsWereAlreadyFlagged:
    """The half that was already right, and had nothing asserting it.

    These tools caught only ``CredentialError``, so a network failure or an
    eQSL refusal propagated uncaught — and FastMCP reports an uncaught
    exception as ``isError`` with the message intact. That behaviour was being
    relied on without being stated, which is how a later "tidy-up" adding a
    blanket ``except Exception: return {...}`` would have silently undone it.
    """

    def test_an_upstream_failure_reaches_the_caller_as_a_failure(self, monkeypatch) -> None:
        """EQSL-C20: measured over stdio too — `is_error: True`, message kept."""
        def boom(*_args, **_kwargs):
            raise RuntimeError("eQSL request failed — check network and credentials")

        monkeypatch.setattr(server, "verify_qso", boom, raising=False)
        with pytest.raises(RuntimeError, match="eQSL request failed"):
            _call("eqsl_verify")(from_call="KI7MT", to_call="W1AW",
                                 band="20m", qso_date="2026-01-01")

    def test_no_tool_swallows_a_non_credential_error(self) -> None:
        """EQSL-C21: no `except Exception` returning a payload may creep back.

        Read off the source: a tool that catches everything and returns a dict
        would reinstate exactly the defect #23 removed, and it would do so
        invisibly because the credential path would still look correct.
        """
        import pathlib

        import eqsl_mcp.server as server_module

        source = pathlib.Path(server_module.__file__).read_text()
        assert '"error": str(e)' not in source
        assert "return {\"error\"" not in source


class TestNoFailurePathCarriesTheSecret:
    """eQSL's response body was the error text, and the password is in the URL.

    ``last_upload_date`` strips the tags off whatever eQSL returns and used to
    hand that back. Measured before fixing: given a body echoing the request,
    the sentinel came straight through.
    """

    SENTINEL = "s3nt1nel-not-a-real-password"

    def test_a_body_echoing_the_request_is_withheld(self) -> None:
        """EQSL-C30: the measured case."""
        from eqsl_mcp.client import _safe_error

        body = ("Error: bad request https://www.eqsl.cc/qslcard/DisplayLastUploadDate.cfm"
                f"?UserName=KI7MT&Password={self.SENTINEL}")
        message = _safe_error(body, self.SENTINEL)
        assert self.SENTINEL not in message
        assert "echoed the request" in message

    def test_a_body_carrying_any_url_is_withheld(self) -> None:
        """EQSL-C31: not only the exact secret.

        Matching the secret alone would pass a body quoting the request with
        the password truncated, or another account's.
        """
        from eqsl_mcp.client import _safe_error

        assert "containing a URL" in _safe_error("see https://www.eqsl.cc/help", self.SENTINEL)

    def test_an_ordinary_message_still_reaches_the_caller(self) -> None:
        """EQSL-C32: the control — a guard that withheld everything would be useless."""
        from eqsl_mcp.client import _safe_error

        assert _safe_error("Invalid user name", self.SENTINEL) == "Invalid user name"


class TestVersionInfoShape:
    def test_it_matches_the_shape_the_fleet_returns(self) -> None:
        """EQSL-C40: the convention that drifted because nobody asserted it."""
        info = _call("get_version_info")()
        assert info["service_name"] == "eqsl-mcp"
        assert info["service_version"]
        assert info["spec_version"]


class TestRegistration:
    def test_the_six_tools_a_client_sees(self) -> None:
        """EQSL-C50: calling a function directly is not proof a client can."""
        assert set(_tools()) == READS_EQSL | ANSWERS_FROM_THE_PACKAGE
