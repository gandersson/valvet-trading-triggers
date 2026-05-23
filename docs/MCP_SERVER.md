# Trading Triggers MCP Server

An MCP (Model Context Protocol) server that exposes the trading-triggers database as 8 tools for AI assistants.

## Overview

This server provides programmatic access to the trading triggers database via stdio transport. It connects to the existing SQLite database at `data/triggers.db` and exposes tools for querying triggers, evaluating them, managing stock tracking, and exporting reports.

## Tools (8 total)

| Tool | Description |
|------|-------------|
| `get_todays_triggers` | List today's active triggers. Optional `symbol` filter. |
| `evaluate_trigger` | Manually evaluate a trigger for a symbol. Records result in DB. |
| `get_historical_accuracy` | Hit-rate stats over time. Optional `symbol` and `days` params. |
| `get_market_summary` | Latest market data for all tracked stocks. Optional `symbol` filter. |
| `add_stock` | Add a new stock to today's tracking with a trigger. |
| `remove_stock` | Deactivate a stock's trigger for today. |
| `get_trigger_stats` | Detailed per-trigger-type statistics. Optional `symbol` filter. |
| `export_to_obsidian` | Export a trading report to the Obsidian vault. |

## Installation

The MCP SDK was installed into the project's virtual environment:

```bash
cd /Users/xandgo/.openclaw/workspace/projects/trading-triggers
source .venv/bin/activate
pip install mcp
```

## Usage

### Running the server

```bash
cd /Users/xandgo/.openclaw/workspace/projects/trading-triggers
source .venv/bin/activate
python src/mcp_server.py
```

The server communicates over stdio using the MCP protocol.

### Connecting from an MCP client

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command="python",
    args=["src/mcp_server.py"],
)

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("get_todays_triggers", {})
```

## Database Schema

The server connects to the existing SQLite database with these tables:

- **triggers** — Daily trigger definitions
- **evaluations** — Evaluation results per trigger
- **market_data** — OHLCV market data
- **trigger_stats** — Aggregated hit/miss statistics

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DB_PATH` | `data/triggers.db` | Path to SQLite database |
| `OBSIDIAN_VAULT` | `~/Vaults/valvet/Valvet` | Obsidian vault directory for exports |

Both are auto-detected from the project layout. Modify `src/mcp_server.py` if your paths differ.

## Testing

```bash
cd /Users/xandgo/.openclaw/workspace/projects/trading-triggers
source .venv/bin/activate
python tests/test_mcp_server.py
```

This runs all 8 tools directly (without MCP transport) for fast validation.

For end-to-end transport testing, see the inline test in the MCP SDK client example above.

## Files

| File | Description |
|------|-------------|
| `src/mcp_server.py` | MCP server implementation (stdio transport, 8 tools) |
| `tests/test_mcp_server.py` | Direct tool tests (no transport) |
| `docs/MCP_SERVER.md` | This documentation |
