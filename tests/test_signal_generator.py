"""Tests for signal_generator — Nivå 3: Köp/sälj-signaler.

Tester för:
- Confidence score-beräkning (N1 * N2 * historisk accuracy)
- Signalstyrka 1-5 mappning
- Köp/sälj-signalgenerering
- Edge cases (noll accuracy, saknade data)
- Hypotetisk P&L-beräkning
"""

import sys
from pathlib import Path

import pytest

# Ensure the project src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signal_generator import (
    _build_recommendation,
    aggregate_signals_by_symbol,
    calculate_confidence_score,
    calculate_hypothetical_pnl,
    filter_signals_by_strength,
    generate_signal,
    map_signal_strength,
)

# =============================================================================
# Confidence Score Calculation
# =============================================================================


class TestCalculateConfidenceScore:
    """Tester för calculate_confidence_score — N1 * N2 * historical_accuracy."""

    def test_perfect_confidence(self):
        """Alla tre faktorer = 1.0 → confidence = 1.0."""
        result = calculate_confidence_score(1.0, 1.0, 1.0)
        assert result == 1.0

    def test_zero_confidence(self):
        """Någon faktor = 0.0 → confidence = 0.0."""
        assert calculate_confidence_score(0.0, 1.0, 1.0) == 0.0
        assert calculate_confidence_score(1.0, 0.0, 1.0) == 0.0
        assert calculate_confidence_score(1.0, 1.0, 0.0) == 0.0

    def test_typical_values(self):
        """Vanliga värden: 0.8 * 0.7 * 0.6 = 0.336."""
        result = calculate_confidence_score(0.8, 0.7, 0.6)
        assert result == pytest.approx(0.336, rel=1e-3)

    def test_low_values(self):
        """Låga värden: 0.3 * 0.4 * 0.2 = 0.024."""
        result = calculate_confidence_score(0.3, 0.4, 0.2)
        assert result == pytest.approx(0.024, rel=1e-3)

    def test_clamped_above_one(self):
        """Värden över 1.0 kläms till 1.0."""
        result = calculate_confidence_score(1.2, 1.5, 2.0)
        assert result == 1.0  # 1.0 * 1.0 * 1.0

    def test_clamped_below_zero(self):
        """Negativa värden kläms till 0.0."""
        result = calculate_confidence_score(-0.5, 0.8, 0.9)
        assert result == 0.0  # 0.0 * 0.8 * 0.9

    def test_mixed_clamping(self):
        """Blandad klämning: -0.5 → 0.0, 1.5 → 1.0, 0.6 → 0.6."""
        result = calculate_confidence_score(-0.5, 1.5, 0.6)
        assert result == 0.0  # 0.0 * 1.0 * 0.6

    def test_returns_float(self):
        """Returnerar en float, inte int."""
        result = calculate_confidence_score(0.5, 0.5, 0.5)
        assert isinstance(result, float)

    def test_rounding(self):
        """Resultatet avrundas till 4 decimaler."""
        result = calculate_confidence_score(0.3333, 0.3333, 0.3333)
        # 0.3333 * 0.3333 * 0.3333 ≈ 0.036992592... → avrundas till 0.0370
        assert result == pytest.approx(0.037, abs=0.0001)


# =============================================================================
# Signal Strength Mapping
# =============================================================================


class TestMapSignalStrength:
    """Tester för map_signal_strength — confidence → styrka 1-5."""

    def test_strength_5_very_strong(self):
        """≥ 0.70 → styrka 5."""
        assert map_signal_strength(0.70) == 5
        assert map_signal_strength(0.85) == 5
        assert map_signal_strength(1.0) == 5

    def test_strength_4_strong(self):
        """≥ 0.50 och < 0.70 → styrka 4."""
        assert map_signal_strength(0.50) == 4
        assert map_signal_strength(0.69) == 4

    def test_strength_3_moderate(self):
        """≥ 0.30 och < 0.50 → styrka 3."""
        assert map_signal_strength(0.30) == 3
        assert map_signal_strength(0.49) == 3

    def test_strength_2_weak(self):
        """≥ 0.15 och < 0.30 → styrka 2."""
        assert map_signal_strength(0.15) == 2
        assert map_signal_strength(0.29) == 2

    def test_strength_1_very_weak(self):
        """< 0.15 → styrka 1."""
        assert map_signal_strength(0.14) == 1
        assert map_signal_strength(0.0) == 1
        assert map_signal_strength(0.01) == 1

    def test_boundary_exact_values(self):
        """Testa exakta gränsvärden."""
        assert map_signal_strength(0.15) == 2
        assert map_signal_strength(0.30) == 3
        assert map_signal_strength(0.50) == 4
        assert map_signal_strength(0.70) == 5

    def test_returns_int(self):
        """Returnerar en int, inte float."""
        result = map_signal_strength(0.5)
        assert isinstance(result, int)


# =============================================================================
# Signal Generation
# =============================================================================


class TestGenerateSignal:
    """Tester för generate_signal — köp/sälj-signalgenerering."""

    def test_bullish_buy_signal(self):
        """Bullish + hög confidence → köp-signal."""
        result = generate_signal("NVDA", "bullish", 0.75)
        assert result is not None
        assert result["symbol"] == "NVDA"
        assert result["signal"] == "buy"
        assert result["direction"] == "bullish"
        assert result["strength"] == 5
        assert result["confidence_score"] == 0.75

    def test_bearish_sell_signal(self):
        """Bearish + hög confidence → sälj-signal."""
        result = generate_signal("WMT", "bearish", 0.60)
        assert result is not None
        assert result["symbol"] == "WMT"
        assert result["signal"] == "sell"
        assert result["direction"] == "bearish"
        assert result["strength"] == 4

    def test_neutral_returns_none(self):
        """Neutral riktning → ingen signal."""
        result = generate_signal("TTWO", "neutral", 0.80)
        assert result is None

    def test_low_confidence_returns_none(self):
        """För låg confidence (styrka 1) → ingen signal."""
        result = generate_signal("ENPH", "bullish", 0.05)
        assert result is None

    def test_strength_2_buy_signal(self):
        """Confidence 0.20 → styrka 2, men fortfarande signal."""
        result = generate_signal("WDAY", "bullish", 0.20)
        assert result is not None
        assert result["strength"] == 2
        assert result["signal"] == "buy"

    def test_strength_3_sell_signal(self):
        """Confidence 0.40 → styrka 3."""
        result = generate_signal("ARM", "bearish", 0.40)
        assert result is not None
        assert result["strength"] == 3
        assert result["signal"] == "sell"

    def test_trigger_result_included(self):
        """trigger_result ska finnas i resultatet."""
        result = generate_signal("NVDA", "bullish", 0.80, trigger_result=True)
        assert result["trigger_result"] is True

        result = generate_signal("NVDA", "bullish", 0.80, trigger_result=False)
        assert result["trigger_result"] is False

    def test_recommendation_present(self):
        """Rekommendationstext ska finnas."""
        result = generate_signal("NVDA", "bullish", 0.80)
        assert "recommendation" in result
        assert "Köp NVDA" in result["recommendation"]
        assert "styrka 5/5" in result["recommendation"]

    def test_case_insensitive_direction(self):
        """Direction ska vara exakt "bullish" eller "bearish"."""
        # Notera: funktionen gör ingen case-insensitive matchning
        result = generate_signal("NVDA", "Bullish", 0.80)
        assert result is None  # "Bullish" != "bullish"

    def test_empty_symbol(self):
        """Tom symbol ska fortfarande fungera."""
        result = generate_signal("", "bullish", 0.80)
        assert result is not None
        assert result["symbol"] == ""


# =============================================================================
# Build Recommendation
# =============================================================================


class TestBuildRecommendation:
    """Tester för _build_recommendation."""

    def test_buy_strength_5(self):
        result = _build_recommendation("buy", 5, "NVDA")
        assert result == "Köp NVDA — mycket stark buy-signal (styrka 5/5)"

    def test_sell_strength_4(self):
        result = _build_recommendation("sell", 4, "WMT")
        assert result == "Sälj WMT — stark sell-signal (styrka 4/5)"

    def test_buy_strength_3(self):
        result = _build_recommendation("buy", 3, "TTWO")
        assert result == "Köp TTWO — måttlig buy-signal (styrka 3/5)"

    def test_sell_strength_2(self):
        result = _build_recommendation("sell", 2, "ENPH")
        assert result == "Sälj ENPH — svag sell-signal (styrka 2/5)"


# =============================================================================
# Hypothetical P&L Calculation
# =============================================================================


class TestCalculateHypotheticalPnL:
    """Tester för calculate_hypothetical_pnl — hypotetisk vinst/förlust."""

    def test_buy_profit(self):
        """Buy-signal + pris stiger → positiv P&L."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert len(results) == 1
        assert results[0]["hypothetical_pnl_pct"] == 10.0

    def test_buy_loss(self):
        """Buy-signal + pris faller → negativ P&L."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 90.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert results[0]["hypothetical_pnl_pct"] == -10.0

    def test_sell_profit(self):
        """Sell-signal + pris faller → positiv P&L."""
        signals = [
            generate_signal("WMT", "bearish", 0.60),
        ]
        price_data = [
            {"symbol": "WMT", "entry_price": 100.0, "exit_price": 90.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert results[0]["hypothetical_pnl_pct"] == 10.0

    def test_sell_loss(self):
        """Sell-signal + pris stiger → negativ P&L."""
        signals = [
            generate_signal("WMT", "bearish", 0.60),
        ]
        price_data = [
            {"symbol": "WMT", "entry_price": 100.0, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert results[0]["hypothetical_pnl_pct"] == -10.0

    def test_multiple_signals(self):
        """Flera signaler med blandade resultat."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            generate_signal("WMT", "bearish", 0.60),
            generate_signal("TTWO", "bullish", 0.40),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 110.0},  # +10%
            {"symbol": "WMT", "entry_price": 100.0, "exit_price": 95.0},  # sell, -5% → +5%
            {"symbol": "TTWO", "entry_price": 100.0, "exit_price": 97.0},  # -3%
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert len(results) == 3
        nvda = next(r for r in results if r["symbol"] == "NVDA")
        wmt = next(r for r in results if r["symbol"] == "WMT")
        ttwo = next(r for r in results if r["symbol"] == "TTWO")
        assert nvda["hypothetical_pnl_pct"] == 10.0
        assert wmt["hypothetical_pnl_pct"] == 5.0
        assert ttwo["hypothetical_pnl_pct"] == -3.0

    def test_empty_signals(self):
        """Tom signallista → tom resultatlista."""
        results = calculate_hypothetical_pnl([], [])
        assert results == []

    def test_empty_price_data(self):
        """Tom prisdatalista → tom resultatlista."""
        signals = [generate_signal("NVDA", "bullish", 0.75)]
        results = calculate_hypothetical_pnl(signals, [])
        assert results == []

    def test_missing_symbol_in_price_data(self):
        """Saknad symbol i prisdata → hoppar över."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "WMT", "entry_price": 100.0, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert results == []

    def test_zero_entry_price(self):
        """entry_price = 0 → division by zero, ska hanteras."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 0.0, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert results == []

    def test_none_prices(self):
        """None-priser ska hanteras."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": None, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert results == []

    def test_position_size(self):
        """Position size ska påverka P&L-amount."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 110.0, "position_size": 10.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        # P&L amount = 10.0 * 10% * 100 = 100.0
        assert results[0]["hypothetical_pnl_amount"] == pytest.approx(100.0, abs=0.01)

    def test_holding_period_days(self):
        """holding_period_days ska finnas i resultatet."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data, holding_period_days=5)
        assert results[0]["holding_period_days"] == 5

    def test_pnl_includes_entry_exit_prices(self):
        """Resultatet ska innehålla entry och exit priser."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        assert results[0]["entry_price"] == 100.0
        assert results[0]["exit_price"] == 110.0

    def test_pnl_preserves_original_signal_data(self):
        """Resultatet ska bevara ursprunglig signal-data."""
        signal = generate_signal("NVDA", "bullish", 0.75)
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 110.0},
        ]
        results = calculate_hypothetical_pnl([signal], price_data)
        assert results[0]["symbol"] == "NVDA"
        assert results[0]["signal"] == "buy"
        assert results[0]["strength"] == 5
        assert results[0]["confidence_score"] == 0.75


# =============================================================================
# Aggregate Signals by Symbol
# =============================================================================


class TestAggregateSignalsBySymbol:
    """Tester för aggregate_signals_by_symbol."""

    def test_single_signal(self):
        """En signal per symbol."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        result = aggregate_signals_by_symbol(signals)
        assert "NVDA" in result
        assert result["NVDA"]["signal_count"] == 1
        assert result["NVDA"]["avg_confidence"] == 0.75
        assert result["NVDA"]["avg_strength"] == 5
        assert result["NVDA"]["buy_count"] == 1
        assert result["NVDA"]["sell_count"] == 0

    def test_multiple_signals_same_symbol(self):
        """Flera signaler för samma symbol."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            generate_signal("NVDA", "bullish", 0.50),
        ]
        result = aggregate_signals_by_symbol(signals)
        assert result["NVDA"]["signal_count"] == 2
        assert result["NVDA"]["avg_confidence"] == pytest.approx(0.625, abs=0.001)
        assert result["NVDA"]["avg_strength"] == pytest.approx(4.5, abs=0.01)

    def test_mixed_buy_sell(self):
        """Både köp- och sälj-signaler för samma symbol."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            generate_signal("NVDA", "bearish", 0.60),
        ]
        result = aggregate_signals_by_symbol(signals)
        assert result["NVDA"]["buy_count"] == 1
        assert result["NVDA"]["sell_count"] == 1
        assert result["NVDA"]["signal_count"] == 2

    def test_multiple_symbols(self):
        """Signaler för flera olika symboler."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            generate_signal("WMT", "bearish", 0.60),
        ]
        result = aggregate_signals_by_symbol(signals)
        assert "NVDA" in result
        assert "WMT" in result
        assert result["NVDA"]["buy_count"] == 1
        assert result["WMT"]["sell_count"] == 1

    def test_empty_signals(self):
        """Tom signallista → tom dict."""
        result = aggregate_signals_by_symbol([])
        assert result == {}

    def test_signals_list_included(self):
        """Varje aggregat ska innehålla listan med signaler."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            generate_signal("NVDA", "bullish", 0.50),
        ]
        result = aggregate_signals_by_symbol(signals)
        assert len(result["NVDA"]["signals"]) == 2


# =============================================================================
# Filter Signals by Strength
# =============================================================================


class TestFilterSignalsByStrength:
    """Tester för filter_signals_by_strength."""

    def test_filter_min_strength_3(self):
        """Behåll bara signaler med styrka ≥ 3."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),  # strength 5
            generate_signal("WMT", "bearish", 0.60),  # strength 4
            generate_signal("TTWO", "bullish", 0.40),  # strength 3
            generate_signal("ENPH", "bullish", 0.20),  # strength 2
            generate_signal("WDAY", "bullish", 0.05),  # None (strength 1)
        ]
        # Remove None values
        signals = [s for s in signals if s is not None]
        result = filter_signals_by_strength(signals, min_strength=3)
        assert len(result) == 3
        assert all(r["strength"] >= 3 for r in result)

    def test_filter_min_strength_4(self):
        """Behåll bara signaler med styrka ≥ 4."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),  # strength 5
            generate_signal("WMT", "bearish", 0.60),  # strength 4
            generate_signal("TTWO", "bullish", 0.40),  # strength 3
        ]
        result = filter_signals_by_strength(signals, min_strength=4)
        assert len(result) == 2
        assert all(r["strength"] >= 4 for r in result)

    def test_filter_all_pass(self):
        """Alla signaler passerar filtret."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            generate_signal("WMT", "bearish", 0.60),
        ]
        result = filter_signals_by_strength(signals, min_strength=1)
        assert len(result) == 2

    def test_filter_none_pass(self):
        """Inga signaler passerar filtret."""
        signals = [
            generate_signal("NVDA", "bullish", 0.20),  # strength 2
            generate_signal("WMT", "bearish", 0.15),  # strength 2
        ]
        result = filter_signals_by_strength(signals, min_strength=3)
        assert len(result) == 0

    def test_empty_signals(self):
        """Tom signallista → tom resultatlista."""
        result = filter_signals_by_strength([], min_strength=3)
        assert result == []


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge cases och felhantering."""

    def test_confidence_with_very_small_values(self):
        """Mycket små värden ska inte krascha."""
        result = calculate_confidence_score(0.01, 0.01, 0.01)
        assert result == pytest.approx(0.000001, abs=1e-6)
        assert map_signal_strength(result) == 1

    def test_confidence_with_very_high_values(self):
        """Värden nära 1.0 ska hanteras korrekt."""
        result = calculate_confidence_score(0.99, 0.99, 0.99)
        assert result > 0.9
        assert map_signal_strength(result) == 5

    def test_generate_signal_with_exact_threshold(self):
        """Exakt vid tröskelvärde för styrka 2."""
        # confidence = 0.15 → strength 2
        result = generate_signal("NVDA", "bullish", 0.15)
        assert result is not None
        assert result["strength"] == 2

    def test_generate_signal_just_below_threshold(self):
        """Precis under tröskelvärdet → ingen signal."""
        result = generate_signal("NVDA", "bullish", 0.149)
        assert result is None

    def test_pnl_with_negative_position_size(self):
        """Negativ position size ska fungera (matematiskt)."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
        ]
        price_data = [
            {"symbol": "NVDA", "entry_price": 100.0, "exit_price": 110.0, "position_size": -1.0},
        ]
        results = calculate_hypothetical_pnl(signals, price_data)
        # P&L amount = -1.0 * 10% * 100 = -10.0
        assert results[0]["hypothetical_pnl_amount"] == pytest.approx(-10.0, abs=0.01)

    def test_aggregate_with_none_signals(self):
        """None-signaler i listan ska hanteras."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            None,
            generate_signal("WMT", "bearish", 0.60),
        ]
        # Skulle krascha om None inte hanteras
        result = aggregate_signals_by_symbol(signals)
        assert "NVDA" in result
        assert "WMT" in result

    def test_filter_with_none_signals(self):
        """None-signaler i listan ska hanteras."""
        signals = [
            generate_signal("NVDA", "bullish", 0.75),
            None,
            generate_signal("WMT", "bearish", 0.60),
        ]
        # Skulle krascha om None inte hanteras
        result = filter_signals_by_strength(signals, min_strength=1)
        assert len(result) == 2


# =============================================================================
# Integration-like tests
# =============================================================================


class TestFullSignalFlow:
    """Integrationstester för hela signalflödet."""

    def test_end_to_end_bullish_scenario(self):
        """Fullt bullish scenario: trigger hit + sektor korrelerar + hög accuracy."""
        # N1 = trigger accuracy 80%
        # N2 = sector correlation 75%
        # Historical = 70%
        confidence = calculate_confidence_score(0.8, 0.75, 0.7)
        assert confidence == pytest.approx(0.42, abs=0.01)

        signal = generate_signal("NVDA", "bullish", confidence)
        assert signal is not None
        assert signal["signal"] == "buy"
        assert signal["strength"] == 3

    def test_end_to_end_bearish_scenario(self):
        """Fullt bearish scenario."""
        confidence = calculate_confidence_score(0.6, 0.8, 0.5)
        assert confidence == pytest.approx(0.24, abs=0.01)

        signal = generate_signal("WMT", "bearish", confidence)
        assert signal is not None
        assert signal["signal"] == "sell"
        assert signal["strength"] == 2

    def test_end_to_end_with_pnl(self):
        """Komplett flödemed P&L-beräkning."""
        confidence = calculate_confidence_score(0.9, 0.8, 0.7)
        signal = generate_signal("NVDA", "bullish", confidence)

        price_data = [
            {"symbol": "NVDA", "entry_price": 200.0, "exit_price": 220.0, "position_size": 5.0},
        ]

        results = calculate_hypothetical_pnl([signal], price_data)
        assert len(results) == 1
        assert results[0]["hypothetical_pnl_pct"] == 10.0
        # 5.0 * 10% * 200 = 100.0
        assert results[0]["hypothetical_pnl_amount"] == pytest.approx(100.0, abs=0.01)

    def test_end_to_end_filter_and_aggregate(self):
        """Komplett flöde med filtrering och aggregering."""
        signals = [
            generate_signal("NVDA", "bullish", 0.8),  # strength 5
            generate_signal("NVDA", "bearish", 0.6),  # strength 4
            generate_signal("WMT", "bullish", 0.4),  # strength 3
            generate_signal("TTWO", "bullish", 0.2),  # strength 2
        ]

        # Filtrera styrka ≥ 3
        filtered = filter_signals_by_strength(signals, min_strength=3)
        assert len(filtered) == 3

        # Aggregera
        aggregated = aggregate_signals_by_symbol(filtered)
        assert "NVDA" in aggregated
        assert "WMT" in aggregated
        assert "TTWO" not in aggregated  # Styrka 2 filtrerades bort

    def test_zero_accuracy_gives_no_signal(self):
        """Noll accuracy → confidence 0 → ingen signal."""
        confidence = calculate_confidence_score(0.0, 0.8, 0.7)
        assert confidence == 0.0

        signal = generate_signal("NVDA", "bullish", confidence)
        assert signal is None

    def test_missing_data_gives_weak_signal(self):
        """Saknade/separata data ger låg confidence."""
        confidence = calculate_confidence_score(0.2, 0.3, 0.1)
        assert confidence == pytest.approx(0.006, abs=0.001)

        signal = generate_signal("NVDA", "bullish", confidence)
        assert signal is None  # Styrka 1 → ingen signal
