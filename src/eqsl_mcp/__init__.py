"""eqsl-mcp: MCP server for eQSL.cc confirmation data."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Final

try:
    _pkg_version = version("eqsl-mcp")
except PackageNotFoundError:  # local dev / editable installs without dist metadata
    _pkg_version = "0.0.0-dev"

__version__: Final[str] = _pkg_version

# Upstream data spec the server is bound to. Pinned to the eQSL.cc endpoint
# contract revision we consume — bump this when eQSL.cc publishes a new
# endpoint contract. Reported by the get_version_info tool so agents can
# detect fleet drift without going outside the MCP protocol.
__spec_version__: Final[str] = "eqsl-cc-v1"
