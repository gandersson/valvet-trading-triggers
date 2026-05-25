#!/usr/bin/env python3
"""Test script for the Trading Triggers MCP Server.

Tests all 8 tools directly (without MCP transport) for speed and reliability.
"""

import asyncio
import sys
from pathlib import Path

# Ensure the project src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_server import (
    _add_stock,
    _evaluate_trigger,
    _export_to_obsidian,
    _get_historical_accuracy,
    _get_market_summary,
    _get_todays_triggers,
    _get_trigger_stats,
)


async def test_all_tools():
    print("=" * 70)
    print("Testing Trading Triggers MCP Server — 8 tools")
    print("=" * 70)

    failures = 0

    # ── 1. get_todays_triggers ────────────────────────────────────────────────
    print("\n[1/8] get_todays_triggers")
    try:
        result = await _get_todays_triggers({})
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── 2. get_todays_triggers with symbol filter ───────────────────────────
    print("\n[2/8] get_todays_triggers (symbol=NVDA)")
    try:
        result = await _get_todays_triggers({"symbol": "NVDA"})
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── 3. get_market_summary ───────────────────────────────────────────────
    print("\n[3/8] get_market_summary")
    try:
        result = await _get_market_summary({})
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── 4. get_trigger_stats ────────────────────────────────────────────────
    print("\n[4/8] get_trigger_stats")
    try:
        result = await _get_trigger_stats({})
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── 5. add_stock ──────────────────────────────────────────────────────────
    print("\n[5/8] add_stock (symbol=TEST)")
    try:
        result = await _add_stock({"symbol": "TEST", "trigger_type": "Open_Above", "condition": "price > open"})
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── 6. evaluate_trigger ───────────────────────────────────────────────────
    print("\n[6/8] evaluate_trigger (symbol=TEST, trigger_type=Open_Above)")
    try:
        result = await _evaluate_trigger(
            {
                "symbol": "TEST",
                "trigger_type": "Open_Above",
                "current_price": 150.0,
                "open_price": 145.0,
            }
        )
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── 7. get_historical_accuracy ──────────────────────────────────────────
    print("\n[7/8] get_historical_accuracy")
    try:
        result = await _get_historical_accuracy({"days": 30})
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── 8. export_to_obsidian ────────────────────────────────────────────────
    print("\n[8/8] export_to_obsidian")
    try:
        result = await _export_to_obsidian({"report_type": "daily"})
        print(result[0].text[:500])
        print("  ✓ PASS")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        failures += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if failures == 0:
        print("ALL 8 TOOLS PASSED ✓")
    else:
        print(f"{failures}/8 TOOLS FAILED ✗")
    print("=" * 70)
    return failures


if __name__ == "__main__":
    exit_code = asyncio.run(test_all_tools())
    sys.exit(exit_code)
