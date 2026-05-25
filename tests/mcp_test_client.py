#!/usr/bin/env python3
"""
Standalone MCP Test Client for Trading Triggers

Connects to src/mcp_server.py via stdio transport and exercises all 8 tools.
Works without OpenClaw — just Python + the project's virtual environment.

Usage:
    cd /Users/xandgo/.openclaw/workspace/projects/trading-triggers
    source .venv/bin/activate
    python tests/mcp_test_client.py
"""

import asyncio
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SERVER_PATH = PROJECT_ROOT / "src" / "mcp_server.py"
DB_PATH = PROJECT_ROOT / "data" / "triggers.db"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def _ensure_test_data():
    """Insert minimal test data if the database is empty."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT COUNT(*) FROM triggers")
    trigger_count = cur.fetchone()[0]

    cur = conn.execute("SELECT COUNT(*) FROM market_data")
    market_count = cur.fetchone()[0]

    today = date.today().isoformat()

    if trigger_count == 0:
        print("  [setup] Inserting test triggers...")
        conn.executemany(
            """
            INSERT INTO triggers (date, symbol, trigger_type, condition, source, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (today, "AAPL", "Open_Above", "price > open", "test_setup", "active"),
                (today, "TSLA", "Momentum", "momentum up", "test_setup", "active"),
            ],
        )
        conn.commit()

    if market_count == 0:
        print("  [setup] Inserting test market data...")
        conn.executemany(
            """
            INSERT INTO market_data (symbol, date, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAPL", today, f"{today} 15:59:00", 180.0, 185.0, 178.0, 183.0, 1000000),
                ("TSLA", today, f"{today} 15:59:00", 250.0, 255.0, 245.0, 252.0, 2000000),
            ],
        )
        conn.commit()

    conn.close()


def _cleanup_test_data():
    """Remove test-setup rows to keep the database clean."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM triggers WHERE source = 'test_setup'")
    conn.execute("DELETE FROM market_data WHERE volume IN (1000000, 2000000)")
    conn.commit()
    conn.close()


async def _send_request(writer, request: dict):
    """Send a JSON-RPC request over stdio."""
    payload = json.dumps(request) + "\n"
    writer.write(payload.encode())
    await writer.drain()


async def _read_response(reader) -> dict:
    """Read a newline-delimited JSON response from stdio."""
    line = await reader.readline()
    if not line:
        raise ConnectionError("Server closed connection unexpectedly")
    return json.loads(line.decode().strip())


async def run_tests():
    print("=" * 70)
    print("Trading Triggers MCP Test Client — stdio transport")
    print("=" * 70)

    # ── 0. Ensure test data ─────────────────────────────────────────────────
    print("\n[0/9] Ensuring test data...")
    _ensure_test_data()
    print("  ✓ Database ready")

    # ── 1. Start server ─────────────────────────────────────────────────────
    print(f"\n[1/9] Starting MCP server: {SERVER_PATH}")
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

    proc = await asyncio.create_subprocess_exec(
        python,
        str(SERVER_PATH),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    print(f"  ✓ Server PID {proc.pid}")

    # ── 2. Initialize ─────────────────────────────────────────────────────────
    print("\n[2/9] Sending initialize request...")
    await _send_request(
        proc.stdin,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-test-client", "version": "1.0.0"},
            },
        },
    )
    init_resp = await _read_response(proc.stdout)
    if "error" in init_resp:
        print(f"  ✗ FAIL: {init_resp['error']}")
        proc.terminate()
        return 1
    server_info = init_resp["result"]["serverInfo"]
    print(f"  ✓ Connected to {server_info['name']} v{server_info['version']}")

    # notifications/initialized
    await _send_request(
        proc.stdin,
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
    )

    # ── 3. List tools ───────────────────────────────────────────────────────
    print("\n[3/9] Listing tools...")
    await _send_request(
        proc.stdin,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    )
    tools_resp = await _read_response(proc.stdout)
    tools = tools_resp["result"]["tools"]
    print(f"  ✓ {len(tools)} tools registered:")
    for t in tools:
        print(f"      - {t['name']}: {t['description'][:60]}...")

    expected_tools = {
        "get_todays_triggers",
        "evaluate_trigger",
        "get_historical_accuracy",
        "get_market_summary",
        "add_stock",
        "remove_stock",
        "get_trigger_stats",
        "export_to_obsidian",
    }
    actual_tools = {t["name"] for t in tools}
    missing = expected_tools - actual_tools
    if missing:
        print(f"  ✗ FAIL: Missing tools: {missing}")
        proc.terminate()
        return 1

    # ── 4–11. Call each tool ─────────────────────────────────────────────────
    failures = 0
    tool_calls = [
        ("get_todays_triggers", {"symbol": "AAPL"}, "Listing today's triggers (AAPL)"),
        ("get_market_summary", {"symbol": "AAPL"}, "Market summary for AAPL"),
        ("add_stock", {"symbol": "MSFT", "trigger_type": "Open_Above", "condition": "price > open"}, "Adding MSFT"),
        (
            "evaluate_trigger",
            {"symbol": "AAPL", "trigger_type": "Open_Above", "current_price": 185.0, "open_price": 180.0},
            "Evaluating AAPL trigger",
        ),
        ("get_historical_accuracy", {"days": 30}, "Historical accuracy (30 days)"),
        ("get_trigger_stats", {"symbol": "AAPL"}, "Trigger stats for AAPL"),
        ("remove_stock", {"symbol": "MSFT"}, "Removing MSFT"),
        ("export_to_obsidian", {"report_type": "daily"}, "Exporting to Obsidian"),
    ]

    for idx, (tool_name, params, label) in enumerate(tool_calls, start=4):
        print(f"\n[{idx}/9] {label} ({tool_name})...")
        await _send_request(
            proc.stdin,
            {
                "jsonrpc": "2.0",
                "id": idx,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
            },
        )
        resp = await _read_response(proc.stdout)
        if "error" in resp:
            print(f"  ✗ FAIL: {resp['error']}")
            failures += 1
        else:
            contents = resp["result"]["content"]
            text = contents[0]["text"][:200].replace("\n", " ")
            print(f"  ✓ PASS — {text}...")

    # ── 12. Cleanup ───────────────────────────────────────────────────────────
    print("\n[9/9] Cleaning up test data...")
    _cleanup_test_data()
    print("  ✓ Test data removed")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if failures == 0:
        print("ALL TESTS PASSED ✓")
    else:
        print(f"{failures} TEST(S) FAILED ✗")
    print("=" * 70)

    proc.terminate()
    await proc.wait()
    return failures


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
