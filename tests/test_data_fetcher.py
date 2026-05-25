"""Tests for data_fetcher module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import pytest
from tenacity import RetryError


class TestDataFetcherYahoo:
    """Test Yahoo Finance data fetching with ticker mapping."""

    def test_fetch_stock_data_yahoo_success(self):
        """Test that Yahoo Finance path works when data is available."""
        df = pd.DataFrame(
            {
                "Open": [150.0, 151.0, 152.0],
                "High": [155.0, 156.0, 157.0],
                "Low": [148.0, 149.0, 150.0],
                "Close": [152.0, 153.0, 154.0],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=[
                pd.Timestamp("2026-05-23 14:30:00"),
                pd.Timestamp("2026-05-23 14:31:00"),
                pd.Timestamp("2026-05-23 14:32:00"),
            ],
        )

        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_class.return_value = mock_ticker

            from data_fetcher import fetch_stock_data_yahoo

            result = fetch_stock_data_yahoo("NVDA")

            assert result["symbol"] == "NVDA"
            assert result["price"] == 154.0
            assert result["open"] == 150.0
            assert result["high"] == 157.0
            assert result["low"] == 148.0
            assert result["volume"] == 1200000
            assert result["source"] == "yahoo"
            assert "timestamp" in result

    def test_fetch_stock_data_yahoo_ticker_mapping(self):
        """Test that OVH is mapped to OVH.PA for Yahoo Finance."""
        df = pd.DataFrame(
            {
                "Open": [11.70],
                "High": [11.90],
                "Low": [11.60],
                "Close": [11.74],
                "Volume": [22704],
            },
            index=[pd.Timestamp("2026-05-25 11:22:00")],
        )

        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_class.return_value = mock_ticker

            from data_fetcher import fetch_stock_data_yahoo

            result = fetch_stock_data_yahoo("OVH")

            # Should return symbol as OVH (the requested symbol)
            assert result["symbol"] == "OVH"
            # But the ticker passed to yfinance should be OVH.PA
            mock_ticker_class.assert_called_once()
            call_args = mock_ticker_class.call_args[0]
            assert call_args[0] == "OVH.PA"

    def test_fetch_stock_data_yahoo_empty_data(self):
        """Test Yahoo Finance path raises on empty data."""
        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_ticker_class.return_value = mock_ticker

            from data_fetcher import fetch_stock_data_yahoo

            with pytest.raises((RetryError, ValueError)):
                fetch_stock_data_yahoo("NVDA")

    def test_fetch_stock_data_with_fallback_for_yahoo_mapped_symbol(self):
        """Test that OVH (mapped symbol) uses Yahoo Finance directly."""
        df = pd.DataFrame(
            {
                "Open": [11.70],
                "High": [11.90],
                "Low": [11.60],
                "Close": [11.74],
                "Volume": [22704],
            },
            index=[pd.Timestamp("2026-05-25 11:22:00")],
        )

        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_class.return_value = mock_ticker

            from data_fetcher import fetch_stock_data_with_fallback

            # OVH is NOT in AVANZA_FALLBACK_SYMBOLS anymore
            result = fetch_stock_data_with_fallback("OVH")
            assert result["source"] == "yahoo"
            assert result["price"] == 11.74

    def test_fetch_stock_data_with_fallback_for_non_fallback_symbol(self):
        """Test that non-fallback symbols use Yahoo Finance directly."""
        df = pd.DataFrame(
            {
                "Open": [150.0],
                "High": [155.0],
                "Low": [148.0],
                "Close": [152.0],
                "Volume": [1000000],
            },
            index=[pd.Timestamp("2026-05-23 14:30:00")],
        )

        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_class.return_value = mock_ticker

            from data_fetcher import fetch_stock_data_with_fallback

            # NVDA is not in AVANZA_FALLBACK_SYMBOLS
            result = fetch_stock_data_with_fallback("NVDA")
            assert result["source"] == "yahoo"

    def test_yahoo_ticker_map_contains_ovh(self):
        """Test that OVH is mapped to OVH.PA."""
        from data_fetcher import YAHOO_TICKER_MAP

        assert "OVH" in YAHOO_TICKER_MAP
        assert YAHOO_TICKER_MAP["OVH"] == "OVH.PA"

    def test_yahoo_ticker_map_contains_eu_symbols(self):
        """Test that multiple EU symbols are mapped with correct suffixes."""
        from data_fetcher import YAHOO_TICKER_MAP

        assert YAHOO_TICKER_MAP.get("ASML") == "ASML.AS"
        assert YAHOO_TICKER_MAP.get("SAP") == "SAP.DE"
        assert YAHOO_TICKER_MAP.get("ADYEN") == "ADYEN.AS"
        assert YAHOO_TICKER_MAP.get("SIE") == "SIE.DE"

    def test_fetch_stock_data_with_fallback_yahoo_fail_avanza_success(self):
        """Test fallback path: Yahoo fails, Avanza succeeds."""
        from data_fetcher import AVANZA_FALLBACK_SYMBOLS, AVANZA_URLS

        html = (
            "<html><body>"
            + " " * 1000  # pad to avoid "too short" check
            + '<dl><dt>Senast betalt</dt><dd>12.34 EUR</dd></dl>'
            + '<p>Högst 12,50 Lägst 12,20</p>'
            + '<span>+2,50% (0,30)</span>'
            + "</body></html>"
        )

        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_ticker_class.return_value = mock_ticker

            with patch(
                "data_fetcher._run_agent_browser", return_value=html
            ):
                from data_fetcher import fetch_stock_data_with_fallback

                result = fetch_stock_data_with_fallback("OVH")

                assert result["source"] == "avanza"
                assert result["symbol"] == "OVH"
                assert result["price"] == 12.34

    def test_fetch_stock_data_with_fallback_both_sources_fail(self):
        """Test that RuntimeError is raised when both Yahoo and Avanza fail."""
        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_ticker_class.return_value = mock_ticker

            with patch(
                "data_fetcher._run_agent_browser",
                side_effect=RuntimeError("Browser timeout"),
            ):
                from data_fetcher import fetch_stock_data_with_fallback

                with pytest.raises(RuntimeError) as exc_info:
                    fetch_stock_data_with_fallback("OVH")

                msg = str(exc_info.value)
                assert "Failed to fetch data for OVH from all sources" in msg
                assert "Yahoo error" in msg
                assert "Avanza error" in msg


class TestAvanzaFallback:
    """Test Avanza fallback parsing (kept for infrastructure)."""

    def test_parse_avanza_price(self):
        """Test Swedish price parsing."""
        from data_fetcher import _parse_avanza_price

        assert _parse_avanza_price("11,74") == 11.74
        assert _parse_avanza_price("11.74") == 11.74
        assert _parse_avanza_price("1 234,56") == 1234.56
        assert _parse_avanza_price("11,74 EUR") == 11.74
        assert _parse_avanza_price("") is None
        assert _parse_avanza_price(None) is None

    def test_parse_avanza_change(self):
        """Test Swedish percentage parsing."""
        from data_fetcher import _parse_avanza_change

        assert _parse_avanza_change("0,00% (0,00)") == 0.0
        assert _parse_avanza_change("+1,29%") == 1.29
        assert _parse_avanza_change("-2,89%") == -2.89
        assert _parse_avanza_change("") is None
        assert _parse_avanza_change(None) is None

    def test_parse_avanza_html_basic(self):
        """Test parsing Avanza HTML for price extraction."""
        from data_fetcher import _parse_avanza_html

        html = """
        <html>
        <body>
            <dl>
                <dt>Senast betalt</dt>
                <dd>11.74 EUR</dd>
            </dl>
            <p>Högst 11,90 Lägst 11,70</p>
            <span>0,00% (0,00)</span>
        </body>
        </html>
        """

        result = _parse_avanza_html(html, "OVH")
        assert result["symbol"] == "OVH"
        assert result["price"] == 11.74
        assert result["high"] == 11.90
        assert result["low"] == 11.70
        assert result["change_pct"] == 0.0
        assert result["open"] == 11.74  # When change is 0, open = price
        assert result["source"] == "avanza"
        assert "timestamp" in result

    def test_parse_avanza_html_with_change(self):
        """Test parsing Avanza HTML with non-zero change."""
        from data_fetcher import _parse_avanza_html

        html = """
        <html>
        <body>
            <dl>
                <dt>Senast betalt</dt>
                <dd>12.34 EUR</dd>
            </dl>
            <p>Högst 12,50 Lägst 12,20</p>
            <span>+2,50% (0,30)</span>
        </body>
        </html>
        """

        result = _parse_avanza_html(html, "OVH")
        assert result["price"] == 12.34
        assert result["high"] == 12.50
        assert result["low"] == 12.20
        assert result["change_pct"] == 2.50
        # open = price / (1 + change/100) = 12.34 / 1.025
        assert abs(result["open"] - 12.04) < 0.01

    def test_avanza_fallback_symbols_contains_eu(self):
        """Test that AVANZA_FALLBACK_SYMBOLS contains EU symbols."""
        from data_fetcher import AVANZA_FALLBACK_SYMBOLS

        assert "OVH" in AVANZA_FALLBACK_SYMBOLS
        assert "ASML" in AVANZA_FALLBACK_SYMBOLS

    def test_avanza_urls_populated(self):
        """Test that AVANZA_URLS contains URLs for fallback symbols."""
        from data_fetcher import AVANZA_URLS

        assert "OVH" in AVANZA_URLS
        assert AVANZA_URLS["OVH"].startswith("https://www.avanza.se/")
        assert "ASML" in AVANZA_URLS
        assert AVANZA_URLS["ASML"].startswith("https://www.avanza.se/")

    def test_fetch_avanza_unsupported_symbol(self):
        """Test that non-configured symbols raise ValueError."""
        from data_fetcher import fetch_avanza_data

        with pytest.raises(ValueError) as exc_info:
            fetch_avanza_data("UNKNOWN")
        assert "not configured" in str(exc_info.value)


class TestDataFetcherCompatibility:
    """Test backward compatibility."""

    def test_fetch_stock_data_compatibility(self):
        """Test that fetch_stock_data is a drop-in replacement."""
        # Should be callable and have the same signature
        import inspect

        from data_fetcher import fetch_stock_data

        sig = inspect.signature(fetch_stock_data)
        params = list(sig.parameters.keys())
        assert "symbol" in params
