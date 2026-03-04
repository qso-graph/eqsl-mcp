"""eqsl-mcp: MCP server for eQSL.cc confirmation data."""

from __future__ import annotations

try:
    from importlib.metadata import version

    __version__ = version("eqsl-mcp")
except Exception:
    __version__ = "0.0.0-dev"
