"""AG (Authenticity Guaranteed) member list with file-based cache."""

from __future__ import annotations

import os
import time
import urllib.request

_AG_URL = "https://www.eqsl.cc/qslcard/DownloadedFiles/AGMemberList.txt"
_CACHE_TTL = 4 * 3600  # 4 hours — list updated ~6x daily


def _cache_path() -> str:
    """Return OS-appropriate cache file path."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    d = os.path.join(base, "eqsl-mcp")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "ag_members.txt")


def _is_fresh(path: str) -> bool:
    """True if the cache file exists and is younger than TTL."""
    try:
        return (time.time() - os.path.getmtime(path)) < _CACHE_TTL
    except OSError:
        return False


def _download_ag_list() -> set[str]:
    """Fetch the AG member list from eQSL and cache it."""
    path = _cache_path()
    req = urllib.request.Request(_AG_URL, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)
    return _parse_ag(data)


def _parse_ag(text: str) -> set[str]:
    """Parse the AG list into a set of uppercase callsigns."""
    calls: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        # Skip header/blank lines — callsigns are alphanumeric+slash
        if not line or line.startswith("#") or line.startswith("List"):
            continue
        # Each line is one callsign
        call = line.split()[0].upper()
        if call.isascii() and len(call) >= 3:
            calls.add(call)
    return calls


def load_ag_set() -> set[str]:
    """Return the AG member set, using cache if fresh."""
    path = _cache_path()
    if _is_fresh(path):
        try:
            with open(path, encoding="utf-8") as f:
                return _parse_ag(f.read())
        except OSError:
            pass
    return _download_ag_list()


def is_ag(callsign: str) -> bool:
    """Check if a callsign has AG status."""
    return callsign.upper() in load_ag_set()
