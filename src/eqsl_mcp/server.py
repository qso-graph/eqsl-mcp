"""eqsl-mcp: MCP server for eQSL.cc confirmation data."""

from __future__ import annotations

import sys

from fastmcp import FastMCP

from qso_graph_auth.identity import PersonaManager
from qso_graph_auth.identity.errors import CredentialError

from . import __version__
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


@mcp.tool()
def eqsl_inbox(
    persona: str,
    since: str | None = None,
    confirmed_only: bool = False,
    unconfirmed_only: bool = False,
    qth_nickname: str | None = None,
) -> dict:
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
        return {"error": str(e)}

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


@mcp.tool()
def eqsl_verify(
    from_call: str,
    to_call: str,
    band: str,
    qso_date: str,
    mode: str | None = None,
) -> dict:
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


@mcp.tool()
def eqsl_ag_check(callsign: str) -> dict:
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
        return {"callsign": callsign.upper(), "ag": None, "error": str(e)}


@mcp.tool()
def eqsl_download(
    persona: str,
    since: str | None = None,
    qth_nickname: str | None = None,
) -> dict:
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
        return {"error": str(e)}


@mcp.tool()
def eqsl_last_upload(persona: str) -> dict:
    """Check when a persona last uploaded QSOs to eQSL.

    Args:
        persona: Persona name configured in adif-mcp.

    Returns:
        Persona name and last upload timestamp.
    """
    try:
        return last_upload_date(_pm(), persona)
    except CredentialError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the eqsl-mcp server."""
    transport = "stdio"
    port = 8001
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--transport" and i < len(sys.argv) - 1:
            transport = sys.argv[i + 1]
        if arg == "--port" and i < len(sys.argv) - 1:
            port = int(sys.argv[i + 1])

    if transport == "streamable-http":
        mcp.run(transport=transport, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
