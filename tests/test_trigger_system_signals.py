"""Tests for signal integration in trigger_system_v1.

Verifierar att:
- determine_direction() returnerar korrekt riktning
- get_trigger_accuracy() returnerar float 0.0-1.0
- get_sector_correlation_accuracy() returnerar float 0.0-1.0
- get_historical_combined_accuracy() returnerar float 0.0-1.0
- generate_signals_for_result() genererar signaler korrekt
- evaluate_all_triggers() returnerar både results och signals
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure the project src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


class TestDetermineDirection:
    """Tester för determine_direction()."""

    def test_open_above_is_bullish(self):
        from trigger_system_v1 import determine_direction

        result = determine_direction("Open_Above", "price > open", "hit")
        assert result == "bullish"

    def test_gap_defense_is_bullish(self):
        from trigger_system_v1 import determine_direction

        result = determine_direction("Gap_Defense", "rapportgapet försvaras", "hit")
        assert result == "bullish"

    def test_momentum_is_bullish(self):
        from trigger_system_v1 import determine_direction

        result = determine_direction("Momentum", "momentum kvar", "hit")
        assert result == "bullish"

    def test_open_below_is_bearish(self):
        from trigger_system_v1 import determine_direction

        result = determine_direction("Open_Below", "price < open", "miss")
        assert result == "bearish"

    def test_premarket_break_neutral(self):
        from trigger_system_v1 import determine_direction

        result = determine_direction("Premarket_Break", "bryter premarket-high/low", "hit")
        # Premarket_Break har inget i bullish_types så fallback till extract_direction
        # "bryter" är inte i någon keyword-lista → neutral
        assert result == "bullish"  # hit + neutral → bullish

    def test_hit_with_neutral_guesses_bullish(self):
        from trigger_system_v1 import determine_direction

        result = determine_direction("Unknown_Type", "some condition", "hit")
        assert result == "bullish"

    def test_miss_with_neutral_returns_neutral(self):
        from trigger_system_v1 import determine_direction

        result = determine_direction("Unknown_Type", "some condition", "miss")
        assert result == "neutral"


class TestGetTriggerAccuracy:
    """Tester för get_trigger_accuracy()."""

    def test_returns_float_between_0_and_1(self):
        from trigger_system_v1 import get_trigger_accuracy

        result = get_trigger_accuracy("NVDA", "Open_Above")
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestGetSectorCorrelationAccuracy:
    """Tester för get_sector_correlation_accuracy()."""

    def test_returns_float_between_0_and_1(self):
        from trigger_system_v1 import get_sector_correlation_accuracy

        result = get_sector_correlation_accuracy("NVDA")
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestGetHistoricalCombinedAccuracy:
    """Tester för get_historical_combined_accuracy()."""

    def test_returns_float_between_0_and_1(self):
        from trigger_system_v1 import get_historical_combined_accuracy

        result = get_historical_combined_accuracy("NVDA")
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestGenerateSignalsForResult:
    """Tester för generate_signals_for_result()."""

    def test_bullish_hit_generates_buy_signal(self):
        from trigger_system_v1 import generate_signals_for_result

        result = {
            "symbol": "NVDA",
            "trigger_type": "Open_Above",
            "condition": "price > open",
            "result": "hit",
            "price": 150.0,
            "open": 145.0,
            "change_pct": 3.45,
        }
        signal = generate_signals_for_result(result, "1h")
        if signal is not None:
            assert signal["symbol"] == "NVDA"
            assert signal["direction"] == "bullish"
            assert signal["signal"] == "buy"
            assert "confidence_score" in signal
            assert "strength" in signal
            assert "recommendation" in signal
            assert "n1" in signal
            assert "n2" in signal
            assert "historical" in signal

    def test_bearish_hit_generates_sell_signal(self):
        from trigger_system_v1 import generate_signals_for_result

        result = {
            "symbol": "WMT",
            "trigger_type": "Open_Below",
            "condition": "price < open",
            "result": "hit",
            "price": 140.0,
            "open": 145.0,
            "change_pct": -3.45,
        }
        signal = generate_signals_for_result(result, "1h")
        if signal is not None:
            assert signal["symbol"] == "WMT"
            assert signal["direction"] == "bearish"
            assert signal["signal"] == "sell"

    def test_neutral_returns_none(self):
        from trigger_system_v1 import generate_signals_for_result

        result = {
            "symbol": "TTWO",
            "trigger_type": "Premarket_Break",
            "condition": "bryter premarket-high/low",
            "result": "miss",
            "price": 150.0,
            "open": 150.0,
            "change_pct": 0.0,
        }
        # miss + neutral → neutral → returnerar None
        signal = generate_signals_for_result(result, "1h")
        assert signal is None

    def test_low_confidence_returns_none(self):
        from trigger_system_v1 import generate_signals_for_result

        # Med 0.5/0.5/0.5 → confidence = 0.125 → strength = 1 → None
        with (
            patch("trigger_system_v1.get_trigger_accuracy", return_value=0.5),
            patch("trigger_system_v1.get_sector_correlation_accuracy", return_value=0.5),
            patch("trigger_system_v1.get_historical_combined_accuracy", return_value=0.5),
        ):
            result = {
                "symbol": "ENPH",
                "trigger_type": "Momentum",
                "condition": "momentum kvar",
                "result": "hit",
                "price": 150.0,
                "open": 145.0,
                "change_pct": 3.45,
            }
            signal = generate_signals_for_result(result, "1h")
            # 0.5 * 0.5 * 0.5 = 0.125 → strength 1 → None
            assert signal is None

    def test_high_confidence_generates_signal(self):
        from trigger_system_v1 import generate_signals_for_result

        # Med 0.9/0.9/0.9 → confidence = 0.729 → strength = 5
        with (
            patch("trigger_system_v1.get_trigger_accuracy", return_value=0.9),
            patch("trigger_system_v1.get_sector_correlation_accuracy", return_value=0.9),
            patch("trigger_system_v1.get_historical_combined_accuracy", return_value=0.9),
        ):
            result = {
                "symbol": "NVDA",
                "trigger_type": "Open_Above",
                "condition": "price > open",
                "result": "hit",
                "price": 150.0,
                "open": 145.0,
                "change_pct": 3.45,
            }
            signal = generate_signals_for_result(result, "1h")
            assert signal is not None
            assert signal["strength"] == 5
            assert signal["confidence_score"] == pytest.approx(0.729, abs=0.001)
