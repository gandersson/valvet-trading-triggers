"""Signal Generator — Nivå 3: Köp/sälj-signaler baserat på N1 * N2 * historical accuracy."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def calculate_confidence_score(
    n1_trigger_accuracy: float,
    n2_sector_accuracy: float,
    historical_accuracy: float,
) -> float:
    """Beräkna confidence score som produkt av N1, N2 och historisk accuracy.

    Args:
        n1_trigger_accuracy: Trigger-träffsäkerhet (0.0–1.0)
        n2_sector_accuracy: Sektor-korrelationsaccuracy (0.0–1.0)
        historical_accuracy: Historisk kombinerad accuracy (0.0–1.0)

    Returns:
        Confidence score mellan 0.0 och 1.0
    """
    # Clamp inputs to valid range
    n1 = max(0.0, min(1.0, n1_trigger_accuracy))
    n2 = max(0.0, min(1.0, n2_sector_accuracy))
    hist = max(0.0, min(1.0, historical_accuracy))

    return round(n1 * n2 * hist, 4)


def map_signal_strength(confidence_score: float) -> int:
    """Mappa confidence score till signalstyrka 1–5.

    Trösklar:
        5: ≥ 0.70 (mycket stark)
        4: ≥ 0.50 (stark)
        3: ≥ 0.30 (måttlig)
        2: ≥ 0.15 (svag)
        1: < 0.15 (mycket svag / avvaktar)

    Args:
        confidence_score: Värde mellan 0.0 och 1.0

    Returns:
        Signalstyrka 1–5
    """
    if confidence_score >= 0.70:
        return 5
    elif confidence_score >= 0.50:
        return 4
    elif confidence_score >= 0.30:
        return 3
    elif confidence_score >= 0.15:
        return 2
    else:
        return 1


def generate_signal(
    symbol: str,
    direction: str,
    confidence_score: float,
    trigger_result: bool = True,
) -> Optional[Dict]:
    """Generera köp- eller sälj-signal baserat på riktning och confidence.

    Args:
        symbol: Aktiesymbol
        direction: "bullish", "bearish" eller "neutral"
        confidence_score: Beräknad confidence score
        trigger_result: True om trigger slog igenom

    Returns:
        Dict med signaldata eller None om ingen signal ska genereras
    """
    if direction not in ("bullish", "bearish"):
        return None

    strength = map_signal_strength(confidence_score)

    # Avvaktar om styrka är 1 (för svag)
    if strength == 1:
        return None

    signal_type = "buy" if direction == "bullish" else "sell"

    return {
        "symbol": symbol,
        "signal": signal_type,
        "direction": direction,
        "strength": strength,
        "confidence_score": round(confidence_score, 4),
        "trigger_result": trigger_result,
        "recommendation": _build_recommendation(signal_type, strength, symbol),
    }


def _build_recommendation(signal_type: str, strength: int, symbol: str) -> str:
    """Bygg en mänsklig läsbar rekommendationstext."""
    strength_words = {
        5: "mycket stark",
        4: "stark",
        3: "måttlig",
        2: "svag",
    }
    word = strength_words.get(strength, "okänd")
    action = "Köp" if signal_type == "buy" else "Sälj"
    return f"{action} {symbol} — {word} {signal_type}-signal (styrka {strength}/5)"


def calculate_hypothetical_pnl(
    signals: List[Dict],
    price_data: List[Dict],
    holding_period_days: int = 1,
) -> List[Dict]:
    """Beräkna hypotetisk P&L för en lista med signaler.

    Args:
        signals: Lista med signal-dicts från generate_signal
        price_data: Lista med prisdata-dicts (symbol, entry_price, exit_price)
        holding_period_days: Antal dagar positionen hålls (för framtida bruk)

    Returns:
        Lista med berikade signal-dicts inklusive hypotetisk P&L
    """
    if not signals or not price_data:
        return []

    # Bygg lookup-dict för prisdata per symbol
    price_lookup: Dict[str, Dict] = {}
    for pd in price_data:
        sym = pd.get("symbol", "").upper()
        if sym:
            price_lookup[sym] = pd

    results = []
    for signal in signals:
        symbol = signal.get("symbol", "").upper()
        if symbol not in price_lookup:
            continue

        prices = price_lookup[symbol]
        entry = prices.get("entry_price")
        exit_p = prices.get("exit_price")

        if entry is None or exit_p is None or entry == 0:
            continue

        signal_type = signal.get("signal", "")
        raw_pnl_pct = (exit_p - entry) / entry * 100

        # För buy-signal: positiv P&L om pris stiger
        # För sell-signal: positiv P&L om pris faller
        if signal_type == "sell":
            pnl_pct = -raw_pnl_pct
        else:
            pnl_pct = raw_pnl_pct

        pnl_amount = prices.get("position_size", 1.0) * (pnl_pct / 100) * entry

        result = dict(signal)
        result["hypothetical_pnl_pct"] = round(pnl_pct, 2)
        result["hypothetical_pnl_amount"] = round(pnl_amount, 2)
        result["entry_price"] = entry
        result["exit_price"] = exit_p
        result["holding_period_days"] = holding_period_days
        results.append(result)

    return results


def aggregate_signals_by_symbol(
    signals: List[Dict],
) -> Dict[str, Dict]:
    """Aggregera signaler per symbol för sammanfattning.

    Args:
        signals: Lista med signal-dicts

    Returns:
        Dict med sammanfattning per symbol
    """
    if not signals:
        return {}

    aggregated: Dict[str, Dict] = {}
    for signal in signals:
        if signal is None:
            continue
        symbol = signal.get("symbol", "")
        if not symbol:
            continue

        if symbol not in aggregated:
            aggregated[symbol] = {
                "symbol": symbol,
                "signal_count": 0,
                "avg_confidence": 0.0,
                "avg_strength": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "signals": [],
            }

        agg = aggregated[symbol]
        agg["signal_count"] += 1
        agg["signals"].append(signal)

        conf = signal.get("confidence_score", 0.0)
        agg["avg_confidence"] = round(
            (agg["avg_confidence"] * (agg["signal_count"] - 1) + conf)
            / agg["signal_count"],
            4,
        )

        strength = signal.get("strength", 0)
        agg["avg_strength"] = round(
            (agg["avg_strength"] * (agg["signal_count"] - 1) + strength)
            / agg["signal_count"],
            2,
        )

        if signal.get("signal") == "buy":
            agg["buy_count"] += 1
        elif signal.get("signal") == "sell":
            agg["sell_count"] += 1

    return aggregated


def filter_signals_by_strength(
    signals: List[Dict],
    min_strength: int = 3,
) -> List[Dict]:
    """Filtrera signaler baserat på minimum styrka.

    Args:
        signals: Lista med signal-dicts
        min_strength: Minsta signalstyrka att inkludera (1–5)

    Returns:
        Filtrerad lista med signaler
    """
    return [
        s for s in signals
        if s is not None and s.get("strength", 0) >= min_strength
    ]
