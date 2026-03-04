# eqsl-mcp

MCP server for [eQSL.cc](https://www.eqsl.cc/) — download incoming eQSLs, verify QSOs, check AG status, and query upload history through any MCP-compatible AI assistant.

Part of the [qso-graph](https://qso-graph.io/) project. Depends on [adif-mcp](https://pypi.org/project/adif-mcp/) for persona and credential management.

## Install

```bash
pip install eqsl-mcp
```

## Tools

| Tool | Auth | Description |
|------|------|-------------|
| `eqsl_inbox` | Yes | Download incoming eQSLs with date/confirmation filters |
| `eqsl_verify` | No | Check if a specific QSO exists in eQSL |
| `eqsl_ag_check` | No | Check if a callsign has AG (Authenticity Guaranteed) status |
| `eqsl_last_upload` | No | When did a persona last upload to eQSL |

## Quick Start

### 1. Set up credentials

eqsl-mcp uses adif-mcp personas for credential management:

```bash
# Install adif-mcp if you haven't
pip install adif-mcp

# Create a persona and add eQSL credentials
adif-mcp persona create ki7mt --callsign KI7MT
adif-mcp persona provider ki7mt eqsl --username KI7MT
adif-mcp persona secret ki7mt eqsl
```

### 2. Configure your MCP client

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "eqsl": {
      "command": "eqsl-mcp"
    }
  }
}
```

**Claude Code** (`.mcp.json`):

```json
{
  "mcpServers": {
    "eqsl": {
      "command": "eqsl-mcp"
    }
  }
}
```

### 3. Ask questions

> "Show me all eQSLs received this week"

> "How many unconfirmed eQSLs do I have on 20m FT8?"

> "Does W1AW have AG status on eQSL?"

> "Verify my QSO with KI7MT on 20m on March 1, 2026"

## Testing Without Credentials

The two public tools (`eqsl_verify` and `eqsl_ag_check`) work without any credentials.

For `eqsl_inbox` testing, set the mock environment variable:

```bash
EQSL_MCP_MOCK=1 eqsl-mcp
```

Or point to a local ADIF file:

```bash
EQSL_MCP_MOCK=1 EQSL_MCP_ADIF=/path/to/test.adi eqsl-mcp
```

## MCP Inspector

```bash
eqsl-mcp --transport streamable-http --port 8001
```

Then open the MCP Inspector at `http://localhost:8001`.

## Development

```bash
git clone https://github.com/qso-graph/eqsl-mcp.git
cd eqsl-mcp
pip install -e .
```

## Date Formats

eQSL uses different date formats across endpoints. eqsl-mcp normalizes everything — you always use `YYYY-MM-DD`:

| You provide | eqsl-mcp sends | Endpoint |
|-------------|----------------|----------|
| `2026-03-01` | `202603010000` | DownloadInBox (RcvdSince) |
| `2026-03-01` | `03/01/2026` | VerifyQSO (QSODate) |

## Mode Matching

eQSL requires exact mode matching. `SSB` won't match `USB`/`LSB`. `PSK` won't match `PSK31`. Use the exact mode logged by the other station.

## License

GPL-3.0-or-later
