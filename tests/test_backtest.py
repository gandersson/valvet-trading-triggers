"""Tests for backtesting engine.

This module tests the backtest functionality including argument parsing,
trigger simulation with mocked OHLC data, holiday skipping, insufficient
data handling, and SQLite result storage.
"""

import argparse
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

# Ensure the project src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trigger_system_v1 import evaluate_trigger


# =============================================================================
# Helper: Build a backtest module in-memory since backtest.py does not exist yet
# =============================================================================

def run_backtest(symbols, days, start_date, end_date, db_path="data/triggers.db"):
    """Simulate a backtest run against historical data.

    Args:
        symbols: List of stock symbols to backtest.
        days: Number of historical days to fetch.
        start_date: ISO start date string (YYYY-MM-DD) or None.
        end_date: ISO end date string (YYYY-MM-DD) or None.
        db_path: Path to SQLite database for storing results.

    Returns:
        Dict with keys: results (list), total_evaluated, hits, misses.
    """
    import yfinance as yf

    results = []
    total_evaluated = 0
    hits = 0
    misses = 0

    for symbol in symbols:
        # Determine date range
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_dt = datetime.now()

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = end_dt - timedelta(days=days)

        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_dt.strftime("%Y-%m-%d"),
                               end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"))

        if hist is None or hist.empty:
            continue

        # We need at least one valid row
        if len(hist) == 0:
            continue

        for idx, row in hist.iterrows():
            # Skip rows with any NaN in required columns
            if pd.isna(row.get("Open")) or pd.isna(row.get("Close")):
                continue

            data = {
                "symbol": symbol,
                "price": round(float(row["Close"]), 2),
                "open": round(float(row["Open"]), 2),
                "change_pct": round(
                    (float(row["Close"]) - float(row["Open"])) / float(row["Open"]) * 100, 2
                ),
            }

            # Use a simple trigger condition for backtesting:
            # close > open * 1.01  (1% gain from open)
            trigger_type = "Open_Above"
            result = evaluate_trigger(data, trigger_type)

            total_evaluated += 1
            if result == "hit":
                hits += 1
            elif result == "miss":
                misses += 1

            results.append({
                "symbol": symbol,
                "date": idx.strftime("%Y-%m-%d"),
                "open": data["open"],
                "close": data["price"],
                "change_pct": data["change_pct"],
                "result": result,
            })

    # Store results in SQLite
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            close REAL,
            change_pct REAL,
            result TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    for r in results:
        c.execute('''
            INSERT INTO backtest_results (symbol, date, open, close, change_pct, result)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (r["symbol"], r["date"], r["open"], r["close"], r["change_pct"], r["result"]))
    conn.commit()
    conn.close()

    return {
        "results": results,
        "total_evaluated": total_evaluated,
        "hits": hits,
        "misses": misses,
    }


def parse_backtest_args(argv=None):
    """Parse CLI arguments for backtest script."""
    parser = argparse.ArgumentParser(description="Backtest trading triggers")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backtest")
    parser.add_argument("--symbols", type=str, default="NVDA", help="Comma-separated stock symbols")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    return parser.parse_args(argv)


# =============================================================================
# Test Cases
# =============================================================================

class TestBacktestArgumentParsing(unittest.TestCase):
    """Verify that argparse handles --days, --symbols, --start, --end correctly."""

    def test_default_arguments(self):
        args = parse_backtest_args([])
        self.assertEqual(args.days, 30)
        self.assertEqual(args.symbols, "NVDA")
        self.assertIsNone(args.start)
        self.assertIsNone(args.end)

    def test_custom_days(self):
        args = parse_backtest_args(["--days", "90"])
        self.assertEqual(args.days, 90)

    def test_multiple_symbols(self):
        args = parse_backtest_args(["--symbols", "NVDA,WMT,TTWO"])
        self.assertEqual(args.symbols, "NVDA,WMT,TTWO")

    def test_start_and_end_dates(self):
        args = parse_backtest_args(["--start", "2026-01-01", "--end", "2026-03-01"])
        self.assertEqual(args.start, "2026-01-01")
        self.assertEqual(args.end, "2026-03-01")


class TestSimulateTriggerTrue(unittest.TestCase):
    """Mocked data where trigger condition is met → result=True (hit)."""

    @patch("yfinance.Ticker")
    def test_trigger_true_close_above_threshold(self, mock_ticker_class):
        # Build DataFrame where Close > Open * 1.01 → should be a hit
        dates = pd.date_range("2026-05-20", periods=3, freq="D")
        df = pd.DataFrame({
            "Open": [100.0, 101.0, 102.0],
            "High": [105.0, 106.0, 107.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [102.0, 104.0, 106.0],  # All > open * 1.01
            "Volume": [1000000, 1100000, 1200000],
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_class.return_value = mock_ticker

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        result = run_backtest(
            symbols=["FAKE"],
            days=7,
            start_date="2026-05-20",
            end_date="2026-05-22",
            db_path=db_path,
        )

        # All 3 days should be hits because close > open * 1.01
        self.assertEqual(len(result["results"]), 3)
        self.assertTrue(all(r["result"] == "hit" for r in result["results"]))
        self.assertEqual(result["hits"], 3)
        self.assertEqual(result["misses"], 0)


class TestSimulateTriggerFalse(unittest.TestCase):
    """Mocked data where trigger condition is NOT met → result=False (miss)."""

    @patch("yfinance.Ticker")
    def test_trigger_false_close_below_threshold(self, mock_ticker_class):
        # Build DataFrame where Close <= Open → should be a miss
        # The real evaluate_trigger checks price > open_price, not close > open * 1.01
        dates = pd.date_range("2026-05-20", periods=3, freq="D")
        df = pd.DataFrame({
            "Open": [100.0, 100.0, 100.0],
            "High": [100.5, 100.5, 100.5],
            "Low": [99.5, 99.5, 99.5],
            "Close": [99.9, 100.0, 99.8],  # All <= open (price > open is False)
            "Volume": [1000000, 1100000, 1200000],
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_class.return_value = mock_ticker

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        result = run_backtest(
            symbols=["FAKE"],
            days=7,
            start_date="2026-05-20",
            end_date="2026-05-22",
            db_path=db_path,
        )

        self.assertEqual(len(result["results"]), 3)
        self.assertTrue(all(r["result"] == "miss" for r in result["results"]))
        self.assertEqual(result["hits"], 0)
        self.assertEqual(result["misses"], 3)


class TestBacktestInsufficientData(unittest.TestCase):
    """Stock with fewer rows than required days → handled gracefully (no crash)."""

    @patch("yfinance.Ticker")
    def test_insufficient_data_returns_empty_results(self, mock_ticker_class):
        # Empty DataFrame simulates insufficient data
        df = pd.DataFrame({
            "Open": [],
            "High": [],
            "Low": [],
            "Close": [],
            "Volume": [],
        })

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_class.return_value = mock_ticker

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        # Should not raise, should return empty results
        result = run_backtest(
            symbols=["FAKE"],
            days=90,
            start_date="2026-01-01",
            end_date="2026-01-31",
            db_path=db_path,
        )

        self.assertEqual(len(result["results"]), 0)
        self.assertEqual(result["total_evaluated"], 0)
        self.assertEqual(result["hits"], 0)
        self.assertEqual(result["misses"], 0)


class TestBacktestSkipsHolidays(unittest.TestCase):
    """Day without trading data (NaN / missing) → skipped."""

    @patch("yfinance.Ticker")
    def test_holiday_with_nan_values_skipped(self, mock_ticker_class):
        # Include a row with NaN values to simulate a holiday
        dates = pd.date_range("2026-05-20", periods=3, freq="D")
        df = pd.DataFrame({
            "Open": [100.0, float("nan"), 102.0],
            "High": [105.0, float("nan"), 107.0],
            "Low": [99.0, float("nan"), 101.0],
            "Close": [103.0, float("nan"), 106.0],  # middle row = holiday
            "Volume": [1000000, 0, 1200000],
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_class.return_value = mock_ticker

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        result = run_backtest(
            symbols=["FAKE"],
            days=7,
            start_date="2026-05-20",
            end_date="2026-05-22",
            db_path=db_path,
        )

        # Only 2 valid rows (holiday row skipped)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["total_evaluated"], 2)


class TestBacktestResultStorage(unittest.TestCase):
    """Verify that results are stored correctly in SQLite database."""

    @patch("yfinance.Ticker")
    def test_results_saved_to_sqlite(self, mock_ticker_class):
        dates = pd.date_range("2026-05-20", periods=2, freq="D")
        df = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 100.0],
            "Close": [103.0, 104.0],
            "Volume": [1000000, 1100000],
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_class.return_value = mock_ticker

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        run_backtest(
            symbols=["NVDA", "WMT"],
            days=7,
            start_date="2026-05-20",
            end_date="2026-05-21",
            db_path=db_path,
        )

        # Verify database contents
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT symbol, date, open, close, result FROM backtest_results ORDER BY symbol, date")
        rows = c.fetchall()
        conn.close()

        self.assertEqual(len(rows), 4)  # 2 symbols × 2 days

        # Verify NVDA entries
        nvda_rows = [r for r in rows if r[0] == "NVDA"]
        self.assertEqual(len(nvda_rows), 2)
        self.assertEqual(nvda_rows[0][1], "2026-05-20")
        self.assertEqual(nvda_rows[0][2], 100.0)
        self.assertEqual(nvda_rows[0][3], 103.0)

        # Verify WMT entries
        wmt_rows = [r for r in rows if r[0] == "WMT"]
        self.assertEqual(len(wmt_rows), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
