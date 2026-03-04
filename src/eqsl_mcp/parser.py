"""Minimal ADIF parser and QSO record types for eQSL responses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TypedDict

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class QsoRecord(TypedDict, total=False):
    """Normalized QSO record from eQSL inbox."""

    call: str
    qso_date: str       # YYYYMMDD
    time_on: str        # HHMM or HHMMSS
    band: str | None
    mode: str | None
    freq: float | None  # MHz
    rst_sent: str | None
    rst_rcvd: str | None
    gridsquare: str | None
    eqsl_qsl_rcvd: str | None   # Y/N/I/…
    eqsl_qslrdate: str | None   # YYYYMMDD
    app_eqsl_ag: str | None     # Y/N
    qslmsg: str | None
    adif: dict[str, str]


@dataclass(frozen=True)
class FetchResult:
    """Container for parsed inbox records."""

    records: list[QsoRecord]


# ---------------------------------------------------------------------------
# ADIF parser
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(
    r"<([A-Za-z0-9_]+):(\d+)(?::[A-Za-z])?>([^<]*)", re.IGNORECASE
)


def parse_adif(text: str) -> list[dict[str, str]]:
    """Extract tag→value pairs per <EOR> from raw ADIF text.

    Not a full ADIF parser — sufficient for eQSL response payloads.
    """
    out: list[dict[str, str]] = []
    current: dict[str, str] = {}
    i = 0
    n = len(text)
    while i < n:
        if text[i : i + 5].upper() == "<EOR>":
            if current:
                out.append(current)
                current = {}
            i += 5
            continue
        m = _FIELD_RE.match(text, i)
        if not m:
            i += 1
            continue
        tag, length_s, value = m.group(1), m.group(2), m.group(3)
        try:
            length = int(length_s)
        except ValueError:
            length = len(value)
        if len(value) < length:
            end = m.end()
            need = length - len(value)
            value = value + text[end : end + need]
            i = end + need
        else:
            i = m.end()
        current[tag.upper()] = value
    if current:
        out.append(current)
    return out


def to_qso(rec: dict[str, str]) -> QsoRecord:
    """Convert a raw ADIF tag dict into a normalized QsoRecord."""

    def _float(s: str | None) -> float | None:
        try:
            return float(s) if s else None
        except Exception:
            return None

    return QsoRecord(
        call=rec.get("CALL", "").upper(),
        qso_date=rec.get("QSO_DATE", ""),
        time_on=rec.get("TIME_ON", ""),
        band=rec.get("BAND"),
        mode=rec.get("MODE"),
        freq=_float(rec.get("FREQ")),
        rst_sent=rec.get("RST_SENT"),
        rst_rcvd=rec.get("RST_RCVD"),
        gridsquare=rec.get("GRIDSQUARE"),
        eqsl_qsl_rcvd=rec.get("EQSL_QSL_RCVD"),
        eqsl_qslrdate=rec.get("EQSL_QSLRDATE"),
        app_eqsl_ag=rec.get("APP_EQSL_AG"),
        qslmsg=rec.get("QSLMSG"),
        adif=rec,
    )


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def to_yyyymmddhhmm(d: str | date | None) -> str:
    """Convert a date to YYYYMMDDHHMM (eQSL RcvdSince format).

    Accepts ISO date strings (YYYY-MM-DD), date objects, or None (→ 30 days ago).
    """
    if d is None:
        dt = datetime.utcnow()
        from datetime import timedelta
        dt = dt - timedelta(days=30)
        return dt.strftime("%Y%m%d0000")
    if isinstance(d, date):
        return d.strftime("%Y%m%d0000")
    try:
        return date.fromisoformat(d).strftime("%Y%m%d0000")
    except Exception:
        return datetime.utcnow().strftime("%Y%m%d0000")


def to_mmddyyyy(d: str) -> str:
    """Convert YYYY-MM-DD to MM/DD/YYYY (eQSL VerifyQSO format)."""
    try:
        dt = date.fromisoformat(d)
        return dt.strftime("%m/%d/%Y")
    except Exception:
        return d
