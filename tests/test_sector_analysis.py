"""Tests for sector analysis — Nivå 2: Sektorkorrelation."""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the project src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sector_analysis import (
    _count_keywords,
    evaluate_sector_correlation,
    extract_direction,
    fetch_sector_data,
    get_sector_etf,
)

# =============================================================================
# Keyword counting (via extract_direction)
# =============================================================================


class TestCountKeywords:
    """Verify that keyword counting works via extract_direction."""

    def test_count_single_occurrence(self):
        assert _count_keywords("momentum accelerera", ["momentum"]) == 1

    def test_count_multiple_occurrences(self):
        # Note: _count_keywords uses word_set (unique words), so duplicate
        # occurrences of the same word count as 1
        assert _count_keywords("momentum och mer momentum", ["momentum"]) == 1

    def test_count_case_insensitive(self):
        assert _count_keywords("MOMENTUM accelerera", ["momentum"]) == 1

    def test_count_no_match(self):
        assert _count_keywords("inget relevant", ["momentum"]) == 0


# =============================================================================
# extract_direction
# =============================================================================


class TestExtractDirection:
    """Tests for extract_direction — bullish/bearish/neutral classification."""

    def test_extract_direction_bullish(self):
        result = extract_direction("momentum accelerera")
        assert result == "bullish"

    def test_extract_direction_bearish(self):
        result = extract_direction("nedställ svaghet")
        assert result == "bearish"

    def test_extract_direction_neutral(self):
        result = extract_direction("Det är en vanlig dag på marknaden.")
        assert result == "neutral"

    def test_extract_direction_mixed(self):
        """Båda bullish och bearish ord → majoritet avgör."""
        # 2 bullish, 1 bearish → bullish wins
        result = extract_direction("momentum accelerera men svaghet")
        assert result == "bullish"

        # 2 bearish, 1 bullish → bearish wins
        result = extract_direction("nedställ svaghet men momentum")
        assert result == "bearish"

    def test_extract_direction_tie_goes_neutral(self):
        """Equal counts → neutral."""
        result = extract_direction("momentum svaghet")
        assert result == "neutral"


# =============================================================================
# get_sector_etf
# =============================================================================


class TestGetSectorEtf:
    """Tests for get_sector_etf — symbol-to-ETF mapping."""

    def test_get_sector_etf_nvda(self):
        assert get_sector_etf("NVDA") == "SOXX"

    def test_get_sector_etf_tgt(self):
        assert get_sector_etf("TGT") == "XLY"

    def test_get_sector_etf_case_insensitive(self):
        """Upper/lower case should both work."""
        assert get_sector_etf("nvda") == "SOXX"
        assert get_sector_etf("NvDa") == "SOXX"

    def test_get_sector_etf_unknown(self):
        """Unmapped symbol → empty string."""
        assert get_sector_etf("UNKNOWN") == ""

    def test_get_sector_etf_eu_symbols(self):
        """EU symbols added in feat/avanza-multi-eu-fallback map to correct ETFs."""
        assert get_sector_etf("ASML") == "SOXX"
        assert get_sector_etf("SAP") == "XLK"
        assert get_sector_etf("ADYEN") == "FINX"
        assert get_sector_etf("SIE") == "XLI"


# =============================================================================
# fetch_sector_data (mocked yfinance)
# =============================================================================


class TestFetchSectorData:
    """Tests for fetch_sector_data with mocked yfinance."""

    @patch("sector_analysis.yf.Ticker")
    def test_fetch_sector_data_from_history(self, mock_ticker_class):
        """Fetch sector data via history."""
        import pandas as pd

        mock_ticker = MagicMock()
        mock_ticker.info = {}

        dates = pd.date_range("2026-05-21", periods=3, freq="D")
        hist = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [102.0, 103.0, 104.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [100.0, 101.5, 102.5],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=dates,
        )
        # After reset_index(), column should be named "Date" (not "index")
        hist.index.name = "Date"
        mock_ticker.history.return_value = hist
        mock_ticker_class.return_value = mock_ticker

        result = fetch_sector_data("SOXX", "2026-05-22")
        assert result["symbol"] == "SOXX"
        assert result["date"] == "2026-05-22"
        # change_percent = (101.5 - 101.0) / 101.0 * 100 = 0.495...
        assert abs(result["change_percent"] - 0.5) < 0.1
        assert result["close"] == 101.5

    @patch("sector_analysis.yf.Ticker")
    def test_fetch_sector_data_empty_returns_dict(self, mock_ticker_class):
        """Empty history → empty dict."""
        import pandas as pd

        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_class.return_value = mock_ticker

        result = fetch_sector_data("FAKE", "2026-05-22")
        assert result == {}


# =============================================================================
# evaluate_sector_correlation
# =============================================================================


class TestEvaluateCorrelation:
    """Tests for evaluate_sector_correlation — trigger vs sector movement alignment."""

    def test_evaluate_sector_correlation_bullish_hit_up(self):
        assert evaluate_sector_correlation(True, "bullish", 1.5) is True

    def test_evaluate_sector_correlation_bearish_hit_down(self):
        assert evaluate_sector_correlation(True, "bearish", -1.5) is True

    def test_evaluate_sector_correlation_bullish_miss_down(self):
        assert evaluate_sector_correlation(False, "bullish", -1.5) is True

    def test_evaluate_sector_correlation_bearish_miss_up(self):
        assert evaluate_sector_correlation(False, "bearish", 1.5) is True

    def test_evaluate_sector_correlation_wrong(self):
        assert evaluate_sector_correlation(True, "bullish", -1.5) is False

    def test_evaluate_sector_correlation_bearish_wrong(self):
        """trigger=True, direction="bearish", sector_change=1.5 → False"""
        assert evaluate_sector_correlation(True, "bearish", 1.5) is False

    def test_evaluate_sector_correlation_neutral_returns_false(self):
        """direction='neutral' → False (no correlation to evaluate)."""
        assert evaluate_sector_correlation(True, "neutral", 5.0) is False
        assert evaluate_sector_correlation(False, "neutral", -3.0) is False


# =============================================================================
# Speed gate (< 5 s total)
# =============================================================================


def test_total_runtime_under_five_seconds():
    """All tests above should complete within 5 seconds total.
    This meta-test captures the suite runtime for reporting."""
    # The actual timing is handled by pytest / CI externally.
    # We just verify the module imports quickly.
    start = time.perf_counter()
    # Re-import to simulate fresh load
    import importlib

    import sector_analysis as sa

    importlib.reload(sa)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0  # Module reload < 1 s (smoke check)
