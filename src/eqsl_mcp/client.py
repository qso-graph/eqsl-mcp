"""HTTP client layer for eQSL.cc endpoints."""

from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
from typing import Any

from adif_mcp.identity import PersonaManager

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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception:
        raise RuntimeError("eQSL request failed — check network and credentials")


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
        return {"persona": persona, "last_upload": None, "error": f"HTTP {status}"}

    # Response is HTML-wrapped — strip tags and extract text content
    text = re.sub(r"<[^>]+>", "", body).strip()
    if not text or "error" in text.lower():
        return {"persona": persona, "last_upload": None, "error": text or "Unknown error"}
    return {"persona": persona, "last_upload": text}
