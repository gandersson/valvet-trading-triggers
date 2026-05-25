#!/usr/bin/env python3
"""
MCP Server for Trading Triggers

Provides 8 tools via stdio transport:
  - get_todays_triggers
  - evaluate_trigger
  - get_historical_accuracy
  - get_market_summary
  - add_stock
  - remove_stock
  - get_trigger_stats
  - export_to_obsidian
"""

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Paths ────────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "data" / "triggers.db"
OBSIDIAN_VAULT = Path.home() / "Vaults" / "valvet" / "Valvet"

# ── Helpers ──────────────────────────────────────────────────────────────────


def _db() -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ── Tool implementations ───────────────────────────────────────────────────────


async def _get_todays_triggers(arguments: dict = None) -> list:
    """List today's active triggers from the database."""
    today = _today_iso()
    symbol_filter = ""
    params = [today]

    if arguments and arguments.get("symbol"):
        symbol_filter = "AND symbol = ?"
        params.append(arguments["symbol"].upper())

    conn = _db()
    cur = conn.execute(
        f"""
        SELECT id, date, symbol, trigger_type, condition, source, status
        FROM triggers
        WHERE date = ? {symbol_filter}
        ORDER BY symbol, trigger_type
        """,
        params,
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return [TextContent(type="text", text=f"No active triggers found for {today}.")]

    report = f"Triggers for {today} ({len(rows)} total):\n"
    report += "=" * 60 + "\n"
    for r in rows:
        report += (
            f"  [{r['symbol']}] {r['trigger_type']} | "
            f"condition: {r['condition']} | "
            f"source: {r['source']} | status: {r['status']}\n"
        )
    return [TextContent(type="text", text=report)]


async def _evaluate_trigger(arguments: dict) -> list:
    """Manually evaluate a specific trigger for a symbol."""
    symbol = arguments.get("symbol", "").upper()
    trigger_type = arguments.get("trigger_type", "")
    current_price = arguments.get("current_price")
    open_price = arguments.get("open_price")

    if not symbol or not trigger_type:
        return [TextContent(type="text", text="Error: 'symbol' and 'trigger_type' are required arguments.")]

    conn = _db()
    cur = conn.execute(
        """
        SELECT id, condition FROM triggers
        WHERE symbol = ? AND trigger_type = ? AND date = ? AND status = 'active'
        ORDER BY id DESC LIMIT 1
        """,
        (symbol, trigger_type, _today_iso()),
    )
    trigger = cur.fetchone()

    if not trigger:
        conn.close()
        return [TextContent(type="text", text=f"No active trigger found for {symbol} / {trigger_type} today.")]

    trigger_id = trigger["id"]
    condition = trigger["condition"]

    # Fetch latest market data if prices not provided
    if current_price is None:
        cur = conn.execute(
            "SELECT close, open FROM market_data WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
            (symbol,),
        )
        row = cur.fetchone()
        if row:
            current_price = row["close"]
            open_price = row["open"] if open_price is None else open_price

    if current_price is None:
        conn.close()
        return [TextContent(type="text", text=f"No market data available for {symbol} and no current_price provided.")]

    # Simple evaluation logic
    result = "hit"
    if condition.lower().startswith("price > open"):
        result = "hit" if current_price > open_price else "miss"
    elif condition.lower().startswith("price < open"):
        result = "hit" if current_price < open_price else "miss"
    elif condition.lower().startswith("bryter"):
        result = "hit"

    # Record evaluation
    eval_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO evaluations (trigger_id, evaluation_time, price_at_eval, open_price, result)
        VALUES (?, ?, ?, ?, ?)
        """,
        (trigger_id, eval_time, current_price, open_price, result),
    )

    # Update trigger_stats
    conn.execute(
        """
        INSERT INTO trigger_stats (symbol, trigger_type, total_evaluated, hits, misses, hit_rate)
        VALUES (?, ?, 1, ?, ?, ?)
        ON CONFLICT(symbol, trigger_type) DO UPDATE SET
            total_evaluated = total_evaluated + 1,
            hits = hits + excluded.hits,
            misses = misses + excluded.misses,
            hit_rate = ROUND(100.0 * (hits + excluded.hits) / (total_evaluated + 1), 2),
            last_updated = CURRENT_TIMESTAMP
        """,
        (
            symbol,
            trigger_type,
            1 if result == "hit" else 0,
            0 if result == "hit" else 1,
            100.0 if result == "hit" else 0.0,
        ),
    )
    conn.commit()
    conn.close()

    report = (
        f"Evaluation for {symbol} ({trigger_type}):\n"
        f"  Condition: {condition}\n"
        f"  Current price: {current_price}\n"
        f"  Open price: {open_price}\n"
        f"  Result: {result.upper()}\n"
    )
    return [TextContent(type="text", text=report)]


async def _get_historical_accuracy(arguments: dict = None) -> list:
    """Get hit-rate statistics over time."""
    symbol = ""
    days = 30
    if arguments:
        symbol = arguments.get("symbol", "").upper()
        days = arguments.get("days", 30)

    since = (datetime.now() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")

    conn = _db()
    where_clause = "WHERE e.evaluation_time >= ?"
    params = [since]
    if symbol:
        where_clause += " AND t.symbol = ?"
        params.append(symbol)

    cur = conn.execute(
        f"""
        SELECT
            t.symbol,
            t.trigger_type,
            COUNT(e.id) AS total,
            SUM(CASE WHEN e.result = 'hit' THEN 1 ELSE 0 END) AS hits,
            SUM(CASE WHEN e.result = 'miss' THEN 1 ELSE 0 END) AS misses,
            ROUND(100.0 * SUM(CASE WHEN e.result = 'hit' THEN 1 ELSE 0 END) / COUNT(e.id), 2) AS hit_rate
        FROM evaluations e
        JOIN triggers t ON e.trigger_id = t.id
        {where_clause}
        GROUP BY t.symbol, t.trigger_type
        ORDER BY hit_rate DESC, total DESC
        """,
        params,
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return [TextContent(type="text", text=f"No evaluation data found for the last {days} days.")]

    header = f"Historical Accuracy (last {days} days):\n"
    header += "=" * 70 + "\n"
    header += f"{'Symbol':<8} {'Trigger':<18} {'Total':>6} {'Hits':>6} {'Misses':>6} {'Hit %':>8}\n"
    header += "-" * 70 + "\n"
    for r in rows:
        header += (
            f"{r['symbol']:<8} {r['trigger_type']:<18} "
            f"{r['total']:>6} {r['hits']:>6} {r['misses']:>6} {r['hit_rate']:>7.1f}%\n"
        )
    return [TextContent(type="text", text=header)]


async def _get_market_summary(arguments: dict = None) -> list:
    """Get latest market data for all tracked stocks."""
    symbol = ""
    if arguments:
        symbol = arguments.get("symbol", "").upper()

    conn = _db()
    where_clause = ""
    params = []
    if symbol:
        where_clause = "WHERE symbol = ?"
        params.append(symbol)

    cur = conn.execute(
        f"""
        SELECT symbol, date, timestamp, open, high, low, close, volume
        FROM market_data
        WHERE (symbol, timestamp) IN (
            SELECT symbol, MAX(timestamp)
            FROM market_data
            {where_clause}
            GROUP BY symbol
        )
        ORDER BY symbol
        """,
        params,
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return [TextContent(type="text", text="No market data available.")]

    report = f"Market Summary ({len(rows)} symbols):\n"
    report += "=" * 85 + "\n"
    report += f"{'Symbol':<8} {'Date':<12} {'Time':<20} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Vol':>8}\n"
    report += "-" * 85 + "\n"
    for r in rows:
        report += (
            f"{r['symbol']:<8} {r['date']:<12} {r['timestamp']:<20} "
            f"{r['open']:>8.2f} {r['high']:>8.2f} {r['low']:>8.2f} {r['close']:>8.2f} {r['volume']:>8}\n"
        )
    return [TextContent(type="text", text=report)]


async def _add_stock(arguments: dict) -> list:
    """Add a new stock to tracking."""
    symbol = arguments.get("symbol", "").upper()
    if not symbol:
        return [TextContent(type="text", text="Error: 'symbol' is required.")]

    trigger_type = arguments.get("trigger_type", "Open_Above")
    condition = arguments.get("condition", "price > open")
    today = _today_iso()

    conn = _db()
    cur = conn.execute(
        "SELECT id FROM triggers WHERE symbol = ? AND date = ? AND status = 'active'",
        (symbol, today),
    )
    if cur.fetchone():
        conn.close()
        return [TextContent(type="text", text=f"{symbol} is already being tracked with an active trigger today.")]

    conn.execute(
        """
        INSERT INTO triggers (date, symbol, trigger_type, condition, source, status)
        VALUES (?, ?, ?, ?, ?, 'active')
        """,
        (today, symbol, trigger_type, condition, "manual_add"),
    )
    conn.commit()
    conn.close()

    return [
        TextContent(
            type="text",
            text=f"Stock {symbol} added to tracking with trigger '{trigger_type}' (condition: {condition}).",
        )
    ]


async def _remove_stock(arguments: dict) -> list:
    """Remove a stock from tracking (deactivate today's trigger)."""
    symbol = arguments.get("symbol", "").upper()
    if not symbol:
        return [TextContent(type="text", text="Error: 'symbol' is required.")]

    today = _today_iso()
    conn = _db()
    cur = conn.execute(
        "UPDATE triggers SET status = 'inactive' WHERE symbol = ? AND date = ? AND status = 'active'",
        (symbol, today),
    )
    updated = cur.rowcount
    conn.commit()
    conn.close()

    if updated:
        return [
            TextContent(
                type="text", text=f"Stock {symbol} removed from today's tracking ({updated} trigger deactivated)."
            )
        ]
    return [TextContent(type="text", text=f"No active trigger found for {symbol} today to remove.")]


async def _get_trigger_stats(arguments: dict = None) -> list:
    """Detailed stats per trigger type."""
    symbol = ""
    if arguments:
        symbol = arguments.get("symbol", "").upper()

    conn = _db()
    where_clause = ""
    params = []
    if symbol:
        where_clause = "WHERE symbol = ?"
        params.append(symbol)

    cur = conn.execute(
        f"""
        SELECT symbol, trigger_type, total_evaluated, hits, misses, hit_rate, last_updated
        FROM trigger_stats
        {where_clause}
        ORDER BY hit_rate DESC, total_evaluated DESC
        """,
        params,
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return [TextContent(type="text", text="No trigger statistics available.")]

    report = f"Trigger Statistics ({len(rows)} records):\n"
    report += "=" * 85 + "\n"
    report += (
        f"{'Symbol':<8} {'Trigger Type':<18} {'Evaluated':>10} {'Hits':>6} {'Misses':>6} {'Hit %':>8} {'Updated':<20}\n"
    )
    report += "-" * 85 + "\n"
    for r in rows:
        report += (
            f"{r['symbol']:<8} {r['trigger_type']:<18} {r['total_evaluated']:>10} "
            f"{r['hits']:>6} {r['misses']:>6} {r['hit_rate']:>7.1f}% {r['last_updated']:<20}\n"
        )
    return [TextContent(type="text", text=report)]


async def _export_to_obsidian(arguments: dict = None) -> list:
    """Export a trading report to the Obsidian vault."""
    report_type = "daily"
    if arguments and arguments.get("report_type"):
        report_type = arguments["report_type"].lower()

    today = _today_iso()
    vault_dir = OBSIDIAN_VAULT
    if not vault_dir.exists():
        vault_dir.mkdir(parents=True, exist_ok=True)

    # Build report content
    conn = _db()

    # Triggers
    cur = conn.execute(
        """
        SELECT id, symbol, trigger_type, condition, source, status
        FROM triggers WHERE date = ? ORDER BY symbol
        """,
        (today,),
    )
    triggers = [dict(r) for r in cur.fetchall()]

    # Stats
    cur = conn.execute(
        """
        SELECT symbol, trigger_type, total_evaluated, hits, misses, hit_rate
        FROM trigger_stats ORDER BY hit_rate DESC
        """,
    )
    stats = [dict(r) for r in cur.fetchall()]

    # Market data summary (latest per symbol)
    cur = conn.execute(
        """
        SELECT symbol, close, open FROM market_data
        WHERE (symbol, timestamp) IN (
            SELECT symbol, MAX(timestamp) FROM market_data GROUP BY symbol
        ) ORDER BY symbol
        """,
    )
    market = [dict(r) for r in cur.fetchall()]
    conn.close()

    filename = f"Trading_Report_{today}_{report_type}.md"
    filepath = vault_dir / filename

    lines = [
        f"# Trading Report — {today} ({report_type.title()})",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        "## Today's Triggers",
        "",
    ]
    if triggers:
        lines.append("| Symbol | Trigger Type | Condition | Source | Status |")
        lines.append("|--------|--------------|-----------|--------|--------|")
        for t in triggers:
            lines.append(f"| {t['symbol']} | {t['trigger_type']} | {t['condition']} | {t['source']} | {t['status']} |")
    else:
        lines.append("No triggers for today.")

    lines.extend(["", "## Trigger Statistics", ""])
    if stats:
        lines.append("| Symbol | Trigger | Evaluated | Hits | Misses | Hit % |")
        lines.append("|--------|---------|-----------|------|--------|-------|")
        for s in stats:
            lines.append(
                f"| {s['symbol']} | {s['trigger_type']} | {s['total_evaluated']} | "
                f"{s['hits']} | {s['misses']} | {s['hit_rate']:.1f}% |"
            )
    else:
        lines.append("No statistics available.")

    lines.extend(["", "## Latest Market Data", ""])
    if market:
        lines.append("| Symbol | Close | Open |")
        lines.append("|--------|-------|------|")
        for m in market:
            lines.append(f"| {m['symbol']} | {m['close']} | {m['open']} |")
    else:
        lines.append("No market data available.")

    filepath.write_text("\n".join(lines), encoding="utf-8")

    return [
        TextContent(
            type="text",
            text=(
                f"Report exported to Obsidian: {filepath}\n"
                f"{len(triggers)} triggers, {len(stats)} stats, "
                f"{len(market)} market records."
            ),
        )
    ]


# ── Tool registry ────────────────────────────────────────────────────────────

TOOL_DISPATCH = {
    "get_todays_triggers": _get_todays_triggers,
    "evaluate_trigger": _evaluate_trigger,
    "get_historical_accuracy": _get_historical_accuracy,
    "get_market_summary": _get_market_summary,
    "add_stock": _add_stock,
    "remove_stock": _remove_stock,
    "get_trigger_stats": _get_trigger_stats,
    "export_to_obsidian": _export_to_obsidian,
}

TOOLS = [
    Tool(
        name="get_todays_triggers",
        description="List today's active triggers from the database. Optionally filter by symbol.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol to filter (optional)"},
            },
        },
    ),
    Tool(
        name="evaluate_trigger",
        description="Manually evaluate a specific trigger for a symbol. Records result to evaluations table.",
        inputSchema={
            "type": "object",
            "required": ["symbol", "trigger_type"],
            "properties": {
                "symbol": {"type": "string"},
                "trigger_type": {"type": "string"},
                "current_price": {"type": "number", "description": "Override current price"},
                "open_price": {"type": "number", "description": "Override open price"},
            },
        },
    ),
    Tool(
        name="get_historical_accuracy",
        description="Get hit-rate statistics over a time window.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Filter by symbol (optional)"},
                "days": {"type": "integer", "default": 30, "description": "Lookback period in days"},
            },
        },
    ),
    Tool(
        name="get_market_summary",
        description="Get latest market data for all tracked stocks.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Filter by symbol (optional)"},
            },
        },
    ),
    Tool(
        name="add_stock",
        description="Add a new stock to today's tracking.",
        inputSchema={
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {"type": "string"},
                "trigger_type": {"type": "string", "default": "Open_Above"},
                "condition": {"type": "string", "default": "price > open"},
            },
        },
    ),
    Tool(
        name="remove_stock",
        description="Remove (deactivate) a stock from today's tracking.",
        inputSchema={
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {"type": "string"},
            },
        },
    ),
    Tool(
        name="get_trigger_stats",
        description="Detailed statistics per trigger type.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Filter by symbol (optional)"},
            },
        },
    ),
    Tool(
        name="export_to_obsidian",
        description="Export a trading report to the Obsidian vault.",
        inputSchema={
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "enum": ["daily", "weekly", "monthly"],
                    "default": "daily",
                },
            },
        },
    ),
]


# ── Server setup ─────────────────────────────────────────────────────────────

server = Server("trading-triggers")


@server.list_tools()
async def list_tools() -> list:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict = None) -> list:
    handler = TOOL_DISPATCH.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments or {})


# ── Entrypoint ───────────────────────────────────────────────────────────────


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
