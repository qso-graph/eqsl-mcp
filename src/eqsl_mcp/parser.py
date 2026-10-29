"""Minimal ADIF parser and QSO record types for eQSL responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TypedDict

from qso_graph_lib import adif

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

def parse_adif(text: str) -> list[dict[str, str]]:
    """Each record's fields, names upper-cased, read by qso_graph_lib.adif.

    The fleet's one ADI reader, as ADIF 3.1.7 defines it. This module's own scanner
    read a Header's fields as the first QSO's (ADIF_VER and PROGRAMID, with trailing
    spaces), and they reached tool results in that QSO's ``adif`` dict.
    """
    return [dict(r.fields) for r in adif.iter_records(text)]


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
