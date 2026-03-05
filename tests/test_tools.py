"""Tool tests for eqsl-mcp — all 5 tools in mock mode."""

from __future__ import annotations

import os

os.environ["EQSL_MCP_MOCK"] = "1"

from eqsl_mcp.server import (
    eqsl_ag_check,
    eqsl_download,
    eqsl_inbox,
    eqsl_last_upload,
    eqsl_verify,
)


# ---------------------------------------------------------------------------
# eqsl_inbox
# ---------------------------------------------------------------------------


class TestEqslInbox:
    def test_returns_records(self):
        result = eqsl_inbox(persona="test")
        assert result["total"] == 2
        assert len(result["records"]) == 2

    def test_confirmed_only(self):
        result = eqsl_inbox(persona="test", confirmed_only=True)
        assert result["total"] == 1
        assert result["records"][0]["call"] == "KI7MT"

    def test_unconfirmed_only(self):
        result = eqsl_inbox(persona="test", unconfirmed_only=True)
        assert result["total"] == 1
        assert result["records"][0]["call"] == "K7ABC"

    def test_band_tally(self):
        result = eqsl_inbox(persona="test")
        bands = {b["band"]: b["count"] for b in result["by_band"]}
        assert bands["20M"] == 1
        assert bands["40M"] == 1


# ---------------------------------------------------------------------------
# eqsl_download
# ---------------------------------------------------------------------------


class TestEqslDownload:
    def test_returns_raw_adif(self):
        result = eqsl_download(persona="test")
        assert "adif" in result
        assert "<EOR>" in result["adif"].upper()

    def test_record_count(self):
        result = eqsl_download(persona="test")
        assert result["record_count"] == 2

    def test_full_history(self):
        result = eqsl_download(persona="test", since=None)
        assert result["record_count"] == 2

    def test_adif_contains_callsigns(self):
        result = eqsl_download(persona="test")
        assert "KI7MT" in result["adif"]
        assert "K7ABC" in result["adif"]


# ---------------------------------------------------------------------------
# eqsl_verify
# ---------------------------------------------------------------------------


class TestEqslVerify:
    def test_verified(self):
        result = eqsl_verify(
            from_call="KI7MT", to_call="W1AW", band="20M", qso_date="2026-03-01"
        )
        assert result["verified"] is True

    def test_ag_status(self):
        result = eqsl_verify(
            from_call="KI7MT", to_call="W1AW", band="20M", qso_date="2026-03-01"
        )
        assert result["ag"] is True


# ---------------------------------------------------------------------------
# eqsl_ag_check
# ---------------------------------------------------------------------------


class TestEqslAgCheck:
    def test_returns_callsign(self):
        result = eqsl_ag_check(callsign="KI7MT")
        assert result["callsign"] == "KI7MT"
        assert "ag" in result


# ---------------------------------------------------------------------------
# eqsl_last_upload
# ---------------------------------------------------------------------------


class TestEqslLastUpload:
    def test_returns_date(self):
        result = eqsl_last_upload(persona="test")
        assert result["persona"] == "test"
        assert result["last_upload"] is not None
