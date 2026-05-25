#!/usr/bin/env python3
"""
Backtesting-motor för Trading Triggers.

Simulerar triggers retroaktivt mot historisk data från Yahoo Finance,
beräknar hypotetisk träffsäkerhet och exporterar resultat.

Usage:
    python src/backtest.py --days 90 --symbols NVDA,WMT,TTWO
    python src/backtest.py --days 30 --all
    python src/backtest.py --start 2026-01-01 --end 2026-03-31 --symbols WDAY,ENPH
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from resilience import retry_yfinance
from sector_analysis import (
    evaluate_sector_correlation,
    extract_direction,
    fetch_sector_data,
    get_sector_etf,
    init_sector_analysis_tables,
    save_sector_analysis,
)

logger = logging.getLogger(__name__)

# === KONFIGURATION ===
DB_PATH = "data/triggers.db"
DEFAULT_STOCKS = ["NVDA", "WMT", "TTWO", "WDAY", "ENPH"]
REPORTS_DIR = "reports"

# NYSE öppnar 09:30 EST. 1h = 10:30 EST, 2h = 12:30 EST
EST_OPEN_HOUR = 9
EST_OPEN_MINUTE = 30
EST_1H_HOUR = 10
EST_1H_MINUTE = 30
EST_2H_HOUR = 12
EST_2H_MINUTE = 30


def get_db_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, timeout=10.0)


def init_backtest_tables() -> None:
    """Skapa backtest_results-tabellen om den inte finns."""
    os.makedirs("data", exist_ok=True)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backtest_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            target_date TEXT NOT NULL,
            evaluation_time TEXT NOT NULL,
            open_price REAL,
            price_at_eval REAL,
            change_pct REAL,
            result TEXT NOT NULL,
            actual_result TEXT,
            actual_price REAL,
            actual_change_pct REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(backtest_date, symbol, evaluation_time, target_date)
        )
        """
    )
    conn.commit()
    conn.close()


# === DATAHÄMTNING ===


@retry_yfinance
def fetch_daily_ohlc(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Hämta daglig OHLCV-data för ett symbol och datumintervall."""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start, end=end, interval="1d")
    if hist is None or hist.empty:
        raise ValueError(f"No daily data returned for {symbol} ({start} to {end})")
    hist = hist.reset_index()
    hist["Date"] = pd.to_datetime(hist["Date"]).dt.tz_localize(None)
    return hist


def _fetch_intraday_data_raw(symbol: str, target_date: date) -> pd.DataFrame:
    """Rå intradag-hämtning utan retry."""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d", interval="1m")
    if hist is None or hist.empty:
        raise ValueError(f"No intraday data returned for {symbol}")
    hist = hist.reset_index()
    hist["Datetime"] = pd.to_datetime(hist["Datetime"]).dt.tz_localize(None)
    mask = hist["Datetime"].dt.date == target_date
    day_data = hist[mask].copy()
    if day_data.empty:
        raise ValueError(f"No intraday data for {symbol} on {target_date}")
    return day_data


@retry_yfinance
def fetch_intraday_data(symbol: str, target_date: date) -> pd.DataFrame:
    """Hämta intradag (1min) data för ett specifikt datum (med retry)."""
    return _fetch_intraday_data_raw(symbol, target_date)


def fetch_historical_intraday_range(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Hämta intradag-data över ett intervall via yfinance (1min / 5min).

    Yahoo Finance tillhandahåller minut-data i begränsade fönster.
    Vi itererar per dag och skippar dagar utan data (helger etc).
    """
    all_frames: list[pd.DataFrame] = []
    current = start
    while current <= end:
        try:
            day_data = _fetch_intraday_data_raw(symbol, current)
            if not day_data.empty:
                all_frames.append(day_data)
        except ValueError:
            pass  # Ingen data för den dagen (helg, framtida datum, långhelg)
        current += timedelta(days=1)
    if not all_frames:
        raise ValueError(f"No intraday data found for {symbol} in range {start} to {end}")
    return pd.concat(all_frames, ignore_index=True)


# === TIDSZONER ===


def est_to_utc(dt: datetime) -> datetime:
    """Konvertera EST/EDT-tid till UTC.

    Yahoo Finance returnerar ofta timestamps i den lokala börsens tidszon
    (EST/EDT för NYSE). För enkelhet antar vi EST som standard,
    men vi använder pandas för robust hantering om möjligt.
    """
    # Yahoo Finance minut-data för US-aktier returneras i EST/EDT
    # pandas har inbyggd tz-handling men yfinance har inte alltid tz-info
    return dt


def get_price_at_time(intraday_df: pd.DataFrame, target_hour: int, target_minute: int) -> float | None:
    """Hämta pris vid specifik tid från intradag-data.

    Returnerar Close-priset för den första minuten ≥ target_time.
    """
    target = target_hour * 60 + target_minute
    intraday_df = intraday_df.copy()
    intraday_df["minute_of_day"] = intraday_df["Datetime"].dt.hour * 60 + intraday_df["Datetime"].dt.minute
    # Hitta första raden >= target
    candidates = intraday_df[intraday_df["minute_of_day"] >= target]
    if candidates.empty:
        return None
    return float(candidates.iloc[0]["Close"])


def get_open_price(intraday_df: pd.DataFrame) -> float | None:
    """Hämta öppningspris från intradag-data."""
    if intraday_df.empty:
        return None
    return float(intraday_df.iloc[0]["Open"])


def get_close_price(intraday_df: pd.DataFrame) -> float | None:
    """Hämta stängningspris från intradag-data (sista Close)."""
    if intraday_df.empty:
        return None
    return float(intraday_df.iloc[-1]["Close"])


# === TRIGGER-SIMULERING ===


def evaluate_condition(open_price: float, price_at_eval: float, condition: str) -> str:
    """Utvärdera ett trigger-villkor.

    Stöder "price > open", "change_pct > X", "change_pct < -X", etc.
    """
    if open_price == 0:
        return "error"
    change_pct = (price_at_eval - open_price) / open_price * 100

    condition_lower = condition.lower().strip()

    if condition_lower == "price > open":
        return "hit" if price_at_eval > open_price else "miss"

    if condition_lower == "price < open":
        return "hit" if price_at_eval < open_price else "miss"

    # Hantera "stigande minst X%" eller "change_pct > X"
    if "stig" in condition_lower or "change_pct >" in condition_lower:
        # Extrahera procenttal om det finns
        import re

        nums = re.findall(r"\d+(?:\.\d+)?", condition_lower)
        if nums:
            threshold = float(nums[0])
            return "hit" if change_pct >= threshold else "miss"
        return "hit" if change_pct > 0 else "miss"

    if "fall" in condition_lower or "change_pct <" in condition_lower:
        import re

        nums = re.findall(r"\d+(?:\.\d+)?", condition_lower)
        if nums:
            threshold = float(nums[0])
            return "hit" if change_pct <= -threshold else "miss"
        return "hit" if change_pct < 0 else "miss"

    if condition_lower == "bryter premarket-high/low":
        # Approximation: stor rörelse i första timmen
        return "hit" if abs(change_pct) > 3 else "miss"

    if "gap" in condition_lower or "försvaras" in condition_lower:
        return "hit" if change_pct > 0 else "miss"

    if "momentum" in condition_lower:
        return "hit" if change_pct > 0 else "miss"

    # Default: positiv = hit
    return "hit" if change_pct > 0 else "miss"


def build_triggers_for_date(target_date: date, symbols: list[str]) -> list[dict]:
    """Bygg trigger-definitioner för en specifik dag.

    Spegelar create_triggers() i trigger_system_v1.py.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    triggers = []
    for symbol in symbols:
        # Standard-triggers per aktie (samma som trigger_system_v1)
        if symbol == "NVDA":
            triggers.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "trigger_type": "Open_Above",
                    "condition": "price > open",
                    "source": "backtest",
                }
            )
        elif symbol == "WMT":
            triggers.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "trigger_type": "Open_Above",
                    "condition": "price > open",
                    "source": "backtest",
                }
            )
        elif symbol == "TTWO":
            triggers.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "trigger_type": "Premarket_Break",
                    "condition": "bryter premarket-high/low",
                    "source": "backtest",
                }
            )
        elif symbol == "WDAY":
            triggers.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "trigger_type": "Gap_Defense",
                    "condition": "rapportgapet försvaras",
                    "source": "backtest",
                }
            )
        elif symbol == "ENPH":
            triggers.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "trigger_type": "Momentum",
                    "condition": "momentum kvar efter uppgradering",
                    "source": "backtest",
                }
            )
        else:
            # Generisk trigger för andra symboler
            triggers.append(
                {
                    "date": date_str,
                    "symbol": symbol,
                    "trigger_type": "Open_Above",
                    "condition": "price > open",
                    "source": "backtest",
                }
            )
    return triggers


# === BACKTEST-KÄRNA ===


def simulate_day(
    symbol: str,
    trigger: dict,
    target_date: date,
    intraday_df: pd.DataFrame | None,
    daily_row: pd.Series | None,
) -> dict | None:
    """Simulera en trigger för en specifik dag.

    Returnerar resultat-dict eller None om data saknas.
    """
    results = []
    evaluation_times = ["1h", "2h", "EOD"]

    open_price = None
    close_price = None

    if intraday_df is not None and not intraday_df.empty:
        open_price = get_open_price(intraday_df)
        close_price = get_close_price(intraday_df)
    elif daily_row is not None:
        open_price = float(daily_row["Open"])
        close_price = float(daily_row["Close"])

    if open_price is None or pd.isna(open_price):
        return None

    for eval_time in evaluation_times:
        price_at_eval = None

        if eval_time == "1h":
            if intraday_df is not None and not intraday_df.empty:
                price_at_eval = get_price_at_time(intraday_df, EST_1H_HOUR, EST_1H_MINUTE)
            else:
                # Approximera från OHLC: använd Open + (High-Low)*0.25
                if daily_row is not None:
                    high = float(daily_row["High"])
                    low = float(daily_row["Low"])
                    price_at_eval = open_price + (high - low) * 0.25
        elif eval_time == "2h":
            if intraday_df is not None and not intraday_df.empty:
                price_at_eval = get_price_at_time(intraday_df, EST_2H_HOUR, EST_2H_MINUTE)
            else:
                if daily_row is not None:
                    high = float(daily_row["High"])
                    low = float(daily_row["Low"])
                    price_at_eval = open_price + (high - low) * 0.5
        elif eval_time == "EOD":
            price_at_eval = close_price

        if price_at_eval is None or pd.isna(price_at_eval):
            continue

        change_pct = round((price_at_eval - open_price) / open_price * 100, 2)
        result = evaluate_condition(open_price, price_at_eval, trigger["condition"])

        results.append(
            {
                "symbol": symbol,
                "trigger_type": trigger["trigger_type"],
                "condition": trigger["condition"],
                "target_date": target_date.strftime("%Y-%m-%d"),
                "evaluation_time": eval_time,
                "open_price": round(open_price, 2),
                "price_at_eval": round(price_at_eval, 2),
                "change_pct": change_pct,
                "result": result,
            }
        )

    return results if results else None


def load_actual_evaluations(symbol: str, target_dates: list[str]) -> dict[tuple[str, str], dict]:
    """Ladda faktiska utvärderingar från evaluations-tabellen.

    Returnerar dict med nyckel (target_date, evaluation_time).
    """
    conn = get_db_connection()
    c = conn.cursor()
    placeholders = ",".join("?" for _ in target_dates)
    # Join triggers -> evaluations
    query = f"""
        SELECT t.symbol, t.trigger_type, e.evaluation_time,
               e.price_at_eval, e.open_price, e.result
        FROM evaluations e
        JOIN triggers t ON e.trigger_id = t.id
        WHERE t.symbol = ? AND t.date IN ({placeholders})
    """
    params = [symbol] + target_dates
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    actuals: dict[tuple[str, str], dict] = {}
    for row in rows:
        sym, trig_type, eval_time, price, open_p, result = row
        key = (sym, eval_time)
        actuals[key] = {
            "symbol": sym,
            "trigger_type": trig_type,
            "evaluation_time": eval_time,
            "price_at_eval": price,
            "open_price": open_p,
            "result": result,
        }
    return actuals


def run_backtest(
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> tuple[list[dict], dict]:
    """Kör backtesting för angivna symboler och datumintervall.

    Returnerar (lista med resultat-rader, summerings-dict).
    """
    all_results: list[dict] = []
    summary: dict = {}

    total_days = (end_date - start_date).days + 1
    trading_days = 0

    for symbol in symbols:
        logger.info("Fetching data for %s...", symbol)
        try:
            daily_df = fetch_daily_ohlc(
                symbol,
                start_date.strftime("%Y-%m-%d"),
                (end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            )
        except ValueError as e:
            logger.warning("%s", e)
            continue

        intraday_df: pd.DataFrame | None = None
        try:
            intraday_df = fetch_historical_intraday_range(symbol, start_date, end_date)
        except ValueError:
            logger.warning("No intraday data for %s, using OHLC approximation", symbol)
            intraday_df = None

        # Ladda faktiska utvärderingar
        target_dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(total_days)]
        actuals = load_actual_evaluations(symbol, target_dates)

        symbol_results = []
        symbol_hits = 0
        symbol_misses = 0
        symbol_evals = 0

        for _, daily_row in daily_df.iterrows():
            target_date = daily_row["Date"].date()
            trading_days += 1

            triggers = build_triggers_for_date(target_date, [symbol])
            for trigger in triggers:
                # Filtrera intradag-data till denna dag
                day_intraday = None
                if intraday_df is not None:
                    mask = intraday_df["Datetime"].dt.date == target_date
                    day_intraday = intraday_df[mask].copy()
                    if day_intraday.empty:
                        day_intraday = None

                sim_results = simulate_day(symbol, trigger, target_date, day_intraday, daily_row)
                if sim_results:
                    for res in sim_results:
                        # Jämför med faktiska resultat om de finns
                        key = (symbol, res["evaluation_time"])
                        if key in actuals:
                            actual = actuals[key]
                            res["actual_result"] = actual["result"]
                            res["actual_price"] = actual["price_at_eval"]
                            if actual["open_price"] and actual["price_at_eval"]:
                                res["actual_change_pct"] = round(
                                    (actual["price_at_eval"] - actual["open_price"]) / actual["open_price"] * 100,
                                    2,
                                )
                            else:
                                res["actual_change_pct"] = None
                        else:
                            res["actual_result"] = None
                            res["actual_price"] = None
                            res["actual_change_pct"] = None

                        symbol_results.append(res)
                        symbol_evals += 1
                        if res["result"] == "hit":
                            symbol_hits += 1
                        elif res["result"] == "miss":
                            symbol_misses += 1

        hit_rate = round(symbol_hits / symbol_evals * 100, 1) if symbol_evals > 0 else 0.0
        summary[symbol] = {
            "triggers": symbol_evals,
            "hits": symbol_hits,
            "misses": symbol_misses,
            "hit_rate": hit_rate,
            "trading_days": len(daily_df),
        }
        all_results.extend(symbol_results)

        logger.info(
            "%s: %s triggers, %s hits, %s misses (%s%% hit rate)",
            symbol, symbol_evals, symbol_hits, symbol_misses, hit_rate,
        )

    return all_results, summary


def _infer_direction_from_trigger_type(trigger_type: str, condition: str) -> str:
    """Försök utleda direction från trigger-typ när texten saknar nyckelord.

    Vissa trigger-typer är implicit bullish/bearish.
    """
    trigger_type_lower = trigger_type.lower()
    condition_lower = condition.lower()

    # Implicit bullish triggers
    bullish_types = {
        "open_above",
        "gap_defense",
        "momentum",
        "breakout",
        "rally",
    }
    if any(bt in trigger_type_lower for bt in bullish_types):
        return "bullish"

    # Implicit bearish triggers
    bearish_types = {
        "open_below",
        "breakdown",
        "weakness",
        "sell_signal",
    }
    if any(bt in trigger_type_lower for bt in bearish_types):
        return "bearish"

    # Kolla condition-texten för implicita signaler
    if "price > open" in condition_lower or "price>open" in condition_lower:
        return "bullish"
    if "price < open" in condition_lower or "price<open" in condition_lower:
        return "bearish"

    # Volatilitets-triggers kan vara riktningsagnostiska
    if "premarket" in trigger_type_lower or "break" in trigger_type_lower:
        # Stor rörelse i första timmen — riktningsagnostisk
        return "neutral"

    return "neutral"


# === DATABAS-PERSISTENS ===


def add_sector_analysis(results: list[dict]) -> list[dict]:
    """Berika backtest-resultat med sektoranalys.

    För varje resultat:
    - Extrahera direction från trigger-text (condition)
    - Hämta sektor-ETF för symbolen
    - Hämta ETF-data för target_date
    - Utvärdera sektorkorrelation
    """
    enriched: list[dict] = []
    sector_cache: dict[tuple[str, str], dict | None] = {}

    for res in results:
        symbol = res["symbol"]
        condition = res.get("condition", "")
        trigger_type = res.get("trigger_type", "")
        target_date = res.get("target_date", "")
        trigger_result = res.get("result") == "hit"

        # Extrahera direction från trigger-text
        direction = extract_direction(condition)

        # Fallback: om direction är neutral, försök utled från trigger-typ
        if direction == "neutral":
            direction = _infer_direction_from_trigger_type(trigger_type, condition)

        # Hämta ETF
        etf = get_sector_etf(symbol)

        # Hämta sektordata (med caching)
        sector_data: dict | None = None
        if etf and target_date:
            cache_key = (etf, target_date)
            if cache_key not in sector_cache:
                sector_data = fetch_sector_data(etf, target_date)
                sector_cache[cache_key] = sector_data
            else:
                sector_data = sector_cache[cache_key]

        # Utvärdera korrelation
        sector_correlated = False
        sector_change_percent: float | None = None
        if sector_data and direction in ("bullish", "bearish"):
            sector_change_percent = sector_data.get("change_percent", 0.0)
            sector_correlated = evaluate_sector_correlation(trigger_result, direction, sector_change_percent)

        enriched_res = dict(res)
        enriched_res["direction"] = direction
        enriched_res["sector_etf"] = etf
        enriched_res["sector_change_percent"] = sector_change_percent
        enriched_res["sector_correlated"] = sector_correlated
        enriched.append(enriched_res)

    total_with_sector = sum(1 for r in enriched if r.get("sector_etf"))
    correlated = sum(1 for r in enriched if r.get("sector_correlated"))
    if total_with_sector > 0:
        accuracy = correlated / total_with_sector * 100
        logger.info(
            "Sector analysis: %s with sector data, %s correct (%.1f%%)",
            total_with_sector, correlated, accuracy,
        )

    return enriched


def save_backtest_results(results: list[dict]) -> None:
    """Spara backtest-resultat och sektoranalys till databasen."""
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    for res in results:
        # Spara huvudresultatet
        c.execute(
            """
            INSERT OR REPLACE INTO backtest_results
            (backtest_date, symbol, trigger_type, condition, target_date,
             evaluation_time, open_price, price_at_eval, change_pct, result,
             actual_result, actual_price, actual_change_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                today,
                res["symbol"],
                res["trigger_type"],
                res["condition"],
                res["target_date"],
                res["evaluation_time"],
                res["open_price"],
                res["price_at_eval"],
                res["change_pct"],
                res["result"],
                res.get("actual_result"),
                res.get("actual_price"),
                res.get("actual_change_pct"),
            ),
        )

        # Spara sektoranalys om den finns
        if res.get("sector_etf") and res.get("direction") in ("bullish", "bearish"):
            # Hämta senaste backtest_result_id via ROWID
            backtest_result_id = c.lastrowid
            if backtest_result_id:
                save_sector_analysis(
                    backtest_result_id=backtest_result_id,
                    symbol=res["symbol"],
                    target_date=res["target_date"],
                    evaluation_time=res["evaluation_time"],
                    direction=res["direction"],
                    sector_etf=res["sector_etf"],
                    sector_change_percent=res.get("sector_change_percent", 0.0) or 0.0,
                    sector_correlated=res.get("sector_correlated", False),
                )

    conn.commit()
    conn.close()
    logger.info("Saved %s results to database", len(results))


# === MARKDOWN-EXPORT ===


def export_markdown(results: list[dict], summary: dict, start_date: date, end_date: date) -> str:
    """Exportera backtest-resultat som markdown.

    Returnerar filnamn.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = os.path.join(
        REPORTS_DIR,
        f"backtest_report_{datetime.now().strftime('%Y-%m-%d')}.md",
    )

    lines: list[str] = []
    lines.append("# 📊 Backtest-rapport — Trading Triggers")
    lines.append("")
    lines.append(f"**Period:** {start_date} till {end_date}")
    lines.append(f"**Genererad:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Summering per aktie
    lines.append("## Summering per aktie")
    lines.append("")
    lines.append("| Aktie | Antal triggers | Träff | Miss | Träffsäkerhet | Handelsdagar |")
    lines.append("|-------|---------------|-------|------|---------------|-------------|")
    for symbol, stats in summary.items():
        lines.append(
            f"| {symbol} | {stats['triggers']} | {stats['hits']} | {stats['misses']} | "
            f"{stats['hit_rate']}% | {stats['trading_days']} |"
        )
    lines.append("")

    lines.append("")

    # Sektorkorrelationsanalys
    sector_results = [r for r in results if r.get("sector_etf")]
    if sector_results:
        lines.append("## Sektorkorrelationsanalys")
        lines.append("")

        total_with_sector = len(sector_results)
        sector_correlated = sum(1 for r in sector_results if r.get("sector_correlated"))
        sector_accuracy = round(sector_correlated / total_with_sector * 100, 1) if total_with_sector > 0 else 0.0

        lines.append(
            f"**Totalt:** {total_with_sector} med sektordata, "
            f"{sector_correlated} korrekta (**{sector_accuracy}%** sektoraccuracy)"
        )
        lines.append("")

        # Per sektor
        per_etf: dict[str, list[dict]] = {}
        for r in sector_results:
            etf = r.get("sector_etf", "")
            if etf:
                per_etf.setdefault(etf, []).append(r)

        lines.append("### Per sektor")
        lines.append("")
        lines.append("| Sektor-ETF | Antal | Korrekta | Accuracy |")
        lines.append("|------------|-------|----------|----------|")
        for etf, etf_results in sorted(per_etf.items()):
            etf_total = len(etf_results)
            etf_correlated = sum(1 for r in etf_results if r.get("sector_correlated"))
            etf_accuracy = round(etf_correlated / etf_total * 100, 1) if etf_total > 0 else 0.0
            lines.append(f"| {etf} | {etf_total} | {etf_correlated} | {etf_accuracy}% |")
        lines.append("")

        # Per riktning
        bullish_results = [r for r in sector_results if r.get("direction") == "bullish"]
        bearish_results = [r for r in sector_results if r.get("direction") == "bearish"]

        lines.append("### Per riktning")
        lines.append("")
        if bullish_results:
            bull_total = len(bullish_results)
            bull_corr = sum(1 for r in bullish_results if r.get("sector_correlated"))
            bull_acc = round(bull_corr / bull_total * 100, 1) if bull_total > 0 else 0.0
            lines.append(f"- **Bullish:** {bull_total} triggers, {bull_corr} korrekta ({bull_acc}%)")
        if bearish_results:
            bear_total = len(bearish_results)
            bear_corr = sum(1 for r in bearish_results if r.get("sector_correlated"))
            bear_acc = round(bear_corr / bear_total * 100, 1) if bear_total > 0 else 0.0
            lines.append(f"- **Bearish:** {bear_total} triggers, {bear_corr} korrekta ({bear_acc}%)")
        lines.append("")

        # Detaljerad sektortabell
        lines.append("### Detaljerad sektorkorrelation")
        lines.append("")
        lines.append("| Datum | Aktie | Riktning | Sektor | Sektorförändring | Korrekt |")
        lines.append("|-------|-------|----------|--------|------------------|----------|")
        for res in sorted(sector_results, key=lambda r: (r["target_date"], r["symbol"])):
            corr_icon = "✅" if res.get("sector_correlated") else "❌"
            sector_chg = res.get("sector_change_percent")
            sector_chg_str = f"{sector_chg:+.2f}%" if sector_chg is not None else "—"
            lines.append(
                f"| {res['target_date']} | {res['symbol']} | {res.get('direction', '?')} | "
                f"{res.get('sector_etf', '—')} | {sector_chg_str} | {corr_icon} |"
            )
        lines.append("")

    # Total summering
    total_triggers = sum(s["triggers"] for s in summary.values())
    total_hits = sum(s["hits"] for s in summary.values())
    total_misses = sum(s["misses"] for s in summary.values())
    total_rate = round(total_hits / total_triggers * 100, 1) if total_triggers > 0 else 0.0
    lines.append(
        f"**Totalt:** {total_triggers} triggers, {total_hits} träff, "
        f"{total_misses} miss (**{total_rate}%** träffsäkerhet)"
    )
    lines.append("")

    # Detaljerad tabell per dag
    lines.append("## Detaljerade resultat per dag")
    lines.append("")
    lines.append("| Datum | Aktie | Trigger | Tid | Öppning | Pris | Förändring | Resultat | Faktiskt |")
    lines.append("|-------|-------|---------|-----|---------|------|------------|----------|----------|")

    # Sortera efter datum
    sorted_results = sorted(results, key=lambda r: (r["target_date"], r["symbol"], r["evaluation_time"]))
    for res in sorted_results:
        emoji = "✅" if res["result"] == "hit" else "❌"
        actual = f"{res['actual_result']} (${res['actual_price']})" if res.get("actual_result") else "—"
        change_str = f"{res['change_pct']:+.2f}%"
        lines.append(
            f"| {res['target_date']} | {res['symbol']} | {res['trigger_type']} | "
            f"{res['evaluation_time']} | ${res['open_price']:.2f} | ${res['price_at_eval']:.2f} | "
            f"{change_str} | {emoji} {res['result']} | {actual} |"
        )
    lines.append("")

    # Jämförelse med faktiska resultat
    actual_matches = [r for r in results if r.get("actual_result")]
    if actual_matches:
        lines.append("## Jämförelse med faktiska utvärderingar")
        lines.append("")
        matches = 0
        mismatches = 0
        for res in actual_matches:
            if res["result"] == res["actual_result"]:
                matches += 1
            else:
                mismatches += 1
        lines.append(
            f"- Överensstämmelse: {matches}/{len(actual_matches)} ({round(matches / len(actual_matches) * 100, 1)}%)"
        )
        lines.append(f"- Avvikelser: {mismatches}")
        lines.append("")
        if mismatches > 0:
            lines.append("### Avvikelser")
            lines.append("")
            lines.append("| Datum | Aktie | Tid | Backtest | Faktiskt |")
            lines.append("|-------|-------|-----|----------|----------|")
            for res in actual_matches:
                if res["result"] != res["actual_result"]:
                    lines.append(
                        f"| {res['target_date']} | {res['symbol']} | "
                        f"{res['evaluation_time']} | {res['result']} | {res['actual_result']} |"
                    )
            lines.append("")
    else:
        lines.append("*Inga faktiska utvärderingar hittades i databasen för denna period.*")
        lines.append("")

    lines.append("---")
    lines.append("_Genererad av Trading Triggers Backtest-motor 🤖📈_")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Report saved: %s", filename)
    return filename


# === ARGUMENT-PARSING ===


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtesting-motor för Trading Triggers")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--days", type=int, help="Antal dagar bakåt att backtesta")
    group.add_argument(
        "--start",
        type=str,
        help="Startdatum (YYYY-MM-DD). Kräver --end.",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="Slutdatum (YYYY-MM-DD). Används med --start.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Komma-separerade symboler, t.ex. NVDA,WMT,TTWO",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Kör för alla standard-aktier",
    )
    return parser.parse_args()


def resolve_dates(args: argparse.Namespace) -> tuple[date, date]:
    """Tolka datum-argument till start och end."""
    if args.days is not None:
        end = date.today()
        start = end - timedelta(days=args.days)
        return start, end
    elif args.start is not None:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        if args.end is not None:
            end = datetime.strptime(args.end, "%Y-%m-%d").date()
        else:
            end = date.today()
        return start, end
    else:
        raise ValueError("Ange antingen --days eller --start/--end")


# === HUVUDPROGRAM ===


def main() -> int:
    args = parse_args()

    # Bestäm symboler
    if args.all:
        symbols = DEFAULT_STOCKS
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = DEFAULT_STOCKS

    # Bestäm datum
    try:
        start_date, end_date = resolve_dates(args)
    except ValueError as e:
        logger.error("%s", e)
        return 1

    print("=" * 70)
    print("🚀 Trading Triggers — Backtesting")
    print("=" * 70)
    print(f"Symboler: {', '.join(symbols)}")
    print(f"Period:   {start_date} till {end_date}")
    print("")

    init_backtest_tables()
    init_sector_analysis_tables()

    results, summary = run_backtest(symbols, start_date, end_date)

    if not results:
        logger.warning("No results to report — check dates and symbols")
        return 1

    logger.info("Running sector correlation analysis...")
    results_with_sector = add_sector_analysis(results)

    save_backtest_results(results_with_sector)
    export_markdown(results_with_sector, summary, start_date, end_date)

    # Print summary
    print("")
    print("=" * 70)
    print("📊 BACKTEST-SAMMANFATTNING")
    print("=" * 70)
    for symbol, stats in summary.items():
        print(
            f"{symbol:6} | {stats['triggers']:3} triggers | "
            f"{stats['hits']:3} träff | {stats['misses']:3} miss | "
            f"{stats['hit_rate']:5.1f}%"
        )
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
