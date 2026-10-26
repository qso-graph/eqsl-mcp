"""eqsl-mcp: MCP server for eQSL.cc confirmation data."""

from __future__ import annotations

import sys
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from qso_graph_auth.identity import PersonaManager
from qso_graph_auth.identity.errors import CredentialError

from . import __spec_version__, __version__
from .ag_cache import is_ag
from .client import download_adif, download_inbox, last_upload_date, verify_qso

mcp = FastMCP(
    "eqsl-mcp",
    version=__version__,
    instructions="MCP server for eQSL.cc — inbox, verification, AG status",
)


def _pm() -> PersonaManager:
    return PersonaManager()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

# MCP 2026-07-28 tool annotations. The defaults are pessimistic — a tool that
# declares nothing is advertised as destructive, non-idempotent and open-world,
# and the specification tells a client to keep a human in the loop for an
# operation like that. Every tool here reads: nothing is uploaded to eQSL and
# no credential is written, only read from the keyring.
#
# openWorldHint is true for the five that reach eqsl.cc — three with the
# operator's credentials, two on public endpoints (QSO verification and the AG
# member list) — and false for get_version_info. They are a client's UX hint
# and never a security control.
_READS_EQSL = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
_ANSWERS_FROM_THE_PACKAGE = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}




def _version_info_payload() -> dict[str, str]:
    """Build the version info envelope. Pulled into a helper so tests can
    call it directly without going through the FastMCP wrapper."""
    return {
        "service_name": "eqsl-mcp",
        "service_version": __version__,
        "spec_version": __spec_version__,
    }


@mcp.tool(annotations=_ANSWERS_FROM_THE_PACKAGE)
def get_version_info() -> dict[str, str]:
    """Get eqsl-mcp service version and upstream eQSL.cc endpoint version.

    Returns the running PyPI version of eqsl-mcp and the eQSL.cc endpoint
    contract in use. Use this to confirm fleet alignment across MCP
    deployments — agents can compare service_version and spec_version
    across servers to detect drift without going outside the MCP protocol.

    Returns:
        service_name, service_version (PyPI), and spec_version (eQSL.cc endpoint).
    """
    return _version_info_payload()


@mcp.tool(annotations=_READS_EQSL)
def eqsl_inbox(
    persona: str,
    since: str | None = None,
    confirmed_only: bool = False,
    unconfirmed_only: bool = False,
    qth_nickname: str | None = None,
) -> dict[str, Any]:
    """Download incoming eQSLs (confirmations others have sent you).

    Args:
        persona: Persona name configured in adif-mcp.
        since: Only records added since this date (YYYY-MM-DD). Default: last 30 days.
        confirmed_only: Only return records you have confirmed back.
        unconfirmed_only: Only return records you have NOT confirmed.
        qth_nickname: QTH profile name (for multi-QTH callsigns).

    Returns:
        Total count, confirmed count, breakdown by band, and QSO records.
    """
    try:
        result = download_inbox(_pm(), persona, since=since, qth_nickname=qth_nickname)
    except CredentialError as e:
        raise ToolError(str(e)) from e

    records = result.records

    if confirmed_only:
        records = [r for r in records if (r.get("eqsl_qsl_rcvd") or "").upper() == "Y"]
    elif unconfirmed_only:
        records = [r for r in records if (r.get("eqsl_qsl_rcvd") or "").upper() != "Y"]

    # Band tally
    tally: dict[str, int] = {}
    confirmed = 0
    for r in records:
        band = (r.get("band") or "UNKNOWN").upper()
        tally[band] = tally.get(band, 0) + 1
        if (r.get("eqsl_qsl_rcvd") or "").upper() == "Y":
            confirmed += 1

    return {
        "total": len(records),
        "confirmed": confirmed,
        "by_band": [{"band": k, "count": v} for k, v in sorted(tally.items())],
        "records": records,
    }


@mcp.tool(annotations=_READS_EQSL)
def eqsl_verify(
    from_call: str,
    to_call: str,
    band: str,
    qso_date: str,
    mode: str | None = None,
) -> dict[str, Any]:
    """Check if a specific QSO exists in eQSL (public, no auth required).

    Args:
        from_call: Sender's callsign.
        to_call: Receiver's callsign.
        band: Band (e.g., '20m').
        qso_date: QSO date in YYYY-MM-DD format.
        mode: Mode (exact match — use 'USB' not 'SSB', 'PSK31' not 'PSK').

    Returns:
        Whether the QSO is verified, AG status, and the raw message.
    """
    return verify_qso(from_call, to_call, band, qso_date, mode)


@mcp.tool(annotations=_READS_EQSL)
def eqsl_ag_check(callsign: str) -> dict[str, Any]:
    """Check if a callsign has Authenticity Guaranteed (AG) status on eQSL.

    Public, no auth required. Uses a cached copy of the AG member list
    (refreshed every 4 hours).

    Args:
        callsign: The callsign to check.

    Returns:
        Callsign and AG status.
    """
    try:
        ag = is_ag(callsign)
        return {"callsign": callsign.upper(), "ag": ag}
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_EQSL)
def eqsl_download(
    persona: str,
    since: str | None = None,
    qth_nickname: str | None = None,
) -> dict[str, Any]:
    """Download your complete eQSL inbox as raw ADIF text.

    Returns the .adi file content — save to disk for import into your logger.
    Omit 'since' to download your entire inbox history.

    Args:
        persona: Persona name configured in adif-mcp.
        since: Only records added since this date (YYYY-MM-DD). Omit for full history.
        qth_nickname: QTH profile name (for multi-QTH callsigns).

    Returns:
        Raw ADIF text and record count.
    """
    try:
        return download_adif(_pm(), persona, since=since, qth_nickname=qth_nickname)
    except CredentialError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_EQSL)
def eqsl_last_upload(persona: str) -> dict[str, Any]:
    """Check when a persona last uploaded QSOs to eQSL.

    Args:
        persona: Persona name configured in adif-mcp.

    Returns:
        Persona name and last upload timestamp.
    """
    try:
        return last_upload_date(_pm(), persona)
    except CredentialError as e:
        raise ToolError(str(e)) from e


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


USAGE = """\
usage: eqsl-mcp [--transport stdio|streamable-http] [--port N] [--version] [--help]

An MCP server: an AI app (Claude Desktop, Claude Code, ...) starts it and talks
to it over stdio. Run on its own it waits for that app; press Ctrl-C to stop.
Set up a client: https://github.com/qso-graph/eqsl-mcp#quick-start

streamable-http binds 127.0.0.1 only: not another machine,
not a container.
"""


def main() -> None:
    """Run the eqsl-mcp server."""
    # Without this the script ignored both flags and bound stdio, so
    # `--help` left a user watching a banner and a hung terminal.
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(USAGE, end="")
        return
    if "--version" in sys.argv[1:]:
        print(f"eqsl-mcp {__version__}")
        return
    transport = "stdio"
    port = 8001
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--transport" and i < len(sys.argv) - 1:
            transport = sys.argv[i + 1]
        if arg == "--port" and i < len(sys.argv) - 1:
            port = int(sys.argv[i + 1])

    # Written out rather than passed through: fastmcp takes a literal, and a
    # str that happens to hold the right word is not the same thing.
    if transport == "streamable-http":
        # Where it bound, said out loud. FastMCP binds 127.0.0.1 and takes
        # no host option, so this is never reachable from another machine
        # or from outside a container. Silent before this line.
        print(
            f"eqsl-mcp on http://127.0.0.1:{port}/mcp - loopback only",
            file=sys.stderr,
        )
        mcp.run(transport="streamable-http", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
