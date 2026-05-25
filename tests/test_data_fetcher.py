"""Tests for data_fetcher module."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import pandas as pd
from tenacity import RetryError


class TestDataFetcherFallback:
    """Test the fallback data fetcher logic."""

    def test_fetch_stock_data_yahoo_success(self):
        """Test that Yahoo Finance path works when data is available."""
        df = pd.DataFrame({
            "Open": [150.0, 151.0, 152.0],
            "High": [155.0, 156.0, 157.0],
            "Low": [148.0, 149.0, 150.0],
            "Close": [152.0, 153.0, 154.0],
            "Volume": [1000000, 1100000, 1200000],
        }, index=[
            pd.Timestamp("2026-05-23 14:30:00"),
            pd.Timestamp("2026-05-23 14:31:00"),
            pd.Timestamp("2026-05-23 14:32:00"),
        ])

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

    def test_fetch_stock_data_yahoo_empty_data(self):
        """Test Yahoo Finance path raises on empty data."""
        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_ticker_class.return_value = mock_ticker

            from data_fetcher import fetch_stock_data_yahoo

            with pytest.raises((RetryError, ValueError)):
                fetch_stock_data_yahoo("NVDA")

    def test_fetch_stock_data_with_fallback_for_non_fallback_symbol(self):
        """Test that non-fallback symbols use Yahoo Finance directly."""
        df = pd.DataFrame({
            "Open": [150.0],
            "High": [155.0],
            "Low": [148.0],
            "Close": [152.0],
            "Volume": [1000000],
        }, index=[pd.Timestamp("2026-05-23 14:30:00")])

        with patch("yfinance.Ticker") as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_class.return_value = mock_ticker

            from data_fetcher import fetch_stock_data_with_fallback

            # NVDA is not in AVANZA_FALLBACK_SYMBOLS
            result = fetch_stock_data_with_fallback("NVDA")
            assert result["source"] == "yahoo"

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

    def test_avanza_fallback_symbol_configured(self):
        """Test that OVH is in the fallback list."""
        from data_fetcher import AVANZA_FALLBACK_SYMBOLS

        assert "OVH" in AVANZA_FALLBACK_SYMBOLS

    def test_avanza_url_configured(self):
        """Test that OVH has an Avanza URL."""
        from data_fetcher import AVANZA_URLS

        assert "OVH" in AVANZA_URLS
        assert "avanza.se" in AVANZA_URLS["OVH"]
        assert "1326722" in AVANZA_URLS["OVH"]

    def test_fetch_avanza_unsupported_symbol(self):
        """Test that non-configured symbols raise ValueError."""
        from data_fetcher import fetch_avanza_data

        with pytest.raises(ValueError) as exc_info:
            fetch_avanza_data("UNKNOWN")
        assert "not configured" in str(exc_info.value)

    @patch("data_fetcher._run_agent_browser")
    def test_fetch_avanza_data_success(self, mock_browser):
        """Test Avanza data fetching with mocked browser."""
        # Need at least 1000 chars to pass the length check
        mock_browser.return_value = """
        <html><head><title>OVH GROUPE (PROM.)EO 1 - Aktie | Avanza</title></head>
        <body>
            <h1>OVH GROUPE (PROM.)EO 1</h1>
            <div class="quote">
                <dl>
                    <dt>Senast betalt</dt>
                    <dd>11.74 EUR</dd>
                </dl>
                <p>Högst 11,90 Lägst 11,70</p>
                <span>0,00% (0,00)</span>
            </div>
            <div class="details">
                <p>Marknadsplats: Euronext Paris</p>
                <p>Kortnamn: OVH</p>
                <p>ISIN: FR0014005HJ9</p>
                <p>P/E-tal: -1902,91</p>
                <p>P/S-tal: 1,57</p>
                <p>P/B-tal: 65,35</p>
                <p>EV/EBIT: 45,03</p>
                <p>Soliditet: 1,51%</p>
                <p>Räntetäckningsgrad: -</p>
                <p>Operativt kassaflöde: 460,1 MEUR</p>
                <p>Räntabilitet eget kapital: -3,43%</p>
                <p>Räntabilitet totalt kapital: -0,05%</p>
                <p>Räntabilitet sysselsatt kapital: 5,07%</p>
                <p>Bruttomarginal: 66,64%</p>
                <p>Rörelsemarginal: 5,97%</p>
                <p>Nettomarginal: -0,19%</p>
                <p>Kapitalomsättningshastighet: 62,97%</p>
                <p>Börsvärde: 1 781,9 MEUR</p>
                <p>Antal aktier: 151 651 536</p>
                <p>Beta: 0,72</p>
                <p>Direktavkastning: -</p>
                <p>Rapportdatum: -</p>
                <p>Blankning: -</p>
                <p>Volatilitet: 46,76%</p>
                <p>Belåningsvärde: 50%</p>
                <p>Godkänd för ränterabatt: Nej</p>
                <p>Blankningsbar: Nej</p>
                <p>Eget kapital/aktie: 0,17 EUR</p>
                <p>Omsättning/aktie: 7,28 EUR</p>
                <p>Vinst/aktie: 0,00 EUR</p>
                <p>Omsättning: -</p>
                <p>Omsättningstillväxt: -</p>
                <p>Vinstmarginal: -</p>
                <p>ROE: -</p>
                <p>ROA: -</p>
                <p>ROCE: -</p>
                <p>EBIT: -</p>
                <p>EBIT-marginal: -</p>
                <p>EBT: -</p>
                <p>Resultat efter skatt: -</p>
                <p>Resultat/aktie: -</p>
                <p>Utdelning/aktie: -</p>
                <p>Utdelningsandel: -</p>
                <p>Fria kassaflödet/aktie: -</p>
                <p>Kassa: -</p>
                <p>Skulder: -</p>
                <p>Räntebärande skulder: -</p>
                <p>Räntebärande skulder/EBITDA: -</p>
                <p>Räntebärande skulder/Eget kapital: -</p>
                <p>Räntebärande skulder/Totala tillgångar: -</p>
                <p>Räntebärande skulder/Omsättning: -</p>
                <p>Räntebärande skulder/Fria kassaflödet: -</p>
                <p>Räntebärande skulder/Resultat före skatt: -</p>
                <p>Räntebärande skulder/Resultat efter skatt: -</p>
                <p>Räntebärande skulder/EBT: -</p>
                <p>Räntebärande skulder/EBIT: -</p>
                <p>Räntebärande skulder/EBITDA: -</p>
                <p>Räntebärande skulder/Resultat/aktie: -</p>
                <p>Räntebärande skulder/Kassa: -</p>
                <p>Räntebärande skulder/Totala skulder: -</p>
                <p>Räntebärande skulder/Eget kapital: -</p>
            </div>
        </body>
        </html>
        """

        from data_fetcher import fetch_avanza_data

        result = fetch_avanza_data("OVH")
        assert result["symbol"] == "OVH"
        assert result["price"] == 11.74
        assert result["high"] == 11.90
        assert result["low"] == 11.70
        assert result["source"] == "avanza"

    @patch("data_fetcher.fetch_stock_data_yahoo")
    @patch("data_fetcher.fetch_avanza_data")
    def test_fallback_chain_yahoo_fails(self, mock_avanza, mock_yahoo):
        """Test that Avanza is used when Yahoo Finance fails."""
        mock_yahoo.side_effect = RetryError("Yahoo failed")
        mock_avanza.return_value = {
            "symbol": "OVH",
            "price": 11.74,
            "open": 11.74,
            "high": 11.90,
            "low": 11.70,
            "volume": 0,
            "change_pct": 0.0,
            "timestamp": "2026-05-25 10:00:00",
            "source": "avanza",
        }

        from data_fetcher import fetch_stock_data_with_fallback

        result = fetch_stock_data_with_fallback("OVH")
        assert result["source"] == "avanza"
        assert result["price"] == 11.74
        mock_yahoo.assert_called_once()
        mock_avanza.assert_called_once()

    @patch("data_fetcher.fetch_stock_data_yahoo")
    @patch("data_fetcher.fetch_avanza_data")
    def test_fallback_chain_yahoo_succeeds(self, mock_avanza, mock_yahoo):
        """Test that Yahoo is used directly when it succeeds."""
        mock_yahoo.return_value = {
            "symbol": "OVH",
            "price": 11.74,
            "open": 11.70,
            "high": 11.90,
            "low": 11.70,
            "volume": 12345,
            "change_pct": 0.34,
            "timestamp": "2026-05-25 10:00:00",
            "source": "yahoo",
        }

        from data_fetcher import fetch_stock_data_with_fallback

        result = fetch_stock_data_with_fallback("OVH")
        assert result["source"] == "yahoo"
        mock_yahoo.assert_called_once()
        mock_avanza.assert_not_called()


class TestDataFetcherIntegration:
    """Integration tests for the data fetcher."""

    def test_fetch_stock_data_compatibility(self):
        """Test that fetch_stock_data is a drop-in replacement."""
        from data_fetcher import fetch_stock_data

        # Should be callable and have the same signature
        import inspect
        sig = inspect.signature(fetch_stock_data)
        params = list(sig.parameters.keys())
        assert "symbol" in params
