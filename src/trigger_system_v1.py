#!/usr/bin/env python3
"""
Trading Trigger System - V1
Hämtar kurser, utvärderar triggers, skickar Discord-meddelande.
"""

import asyncio
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import aiohttp

from data_fetcher import fetch_stock_data_with_fallback
from resilience import discord_circuit_breaker
from signal_generator import (
    calculate_confidence_score,
    generate_signal,
)

logger = logging.getLogger(__name__)


# === Ladda .env-fil ===
def load_env_file():
    """Ladda miljövariabler från config/.env om den finns."""
    env_paths = [
        Path(__file__).parent.parent / "config" / ".env",
        Path.home() / ".config" / "trading-triggers" / ".env",
        Path(".env"),
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key, value)
            break


load_env_file()

# === KONFIGURATION ===
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
STOCKS = ["NVDA", "WMT", "TTWO", "WDAY", "ENPH", "OVH", "ASML", "SAP", "ADYEN", "SIE"]
DB_PATH = "data/triggers.db"


# === DATABAS ===
def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    c = conn.cursor()

    # Triggers-tabell
    c.execute("""
        CREATE TABLE IF NOT EXISTS triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            source TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Utvärderingar — med UNIQUE constraint för idempotens
    c.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id INTEGER NOT NULL,
            evaluation_time TEXT NOT NULL,
            price_at_eval REAL,
            open_price REAL,
            result TEXT NOT NULL,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id),
            UNIQUE(trigger_id, evaluation_time)
        )
    """)

    # Marknadsdata
    c.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            UNIQUE(date, symbol, timestamp)
        )
    """)

    # Historisk statistik
    c.execute("""
        CREATE TABLE IF NOT EXISTS trigger_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            total_evaluated INTEGER DEFAULT 0,
            hits INTEGER DEFAULT 0,
            misses INTEGER DEFAULT 0,
            hit_rate REAL DEFAULT 0.0,
            avg_change_hit REAL DEFAULT 0.0,
            avg_change_miss REAL DEFAULT 0.0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, trigger_type)
        )
    """)

    # Signaler (köp/sälj) från signal_generator
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            evaluation_time TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            trigger_result TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            strength INTEGER NOT NULL,
            confidence_score REAL NOT NULL,
            recommendation TEXT,
            price_at_eval REAL,
            open_price REAL,
            change_pct REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, evaluation_time, symbol, trigger_type)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized")


def get_db_connection():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    if not os.path.exists(DB_PATH):
        init_db()
    return sqlite3.connect(DB_PATH, timeout=10.0)


# === DATAHÄMTNING ===
def fetch_stock_data(symbol: str) -> dict:
    """Hämta aktuell data med automatisk fallback till Avanza.

    För de flesta symboler används Yahoo Finance. För symboler i
    AVANZA_FALLBACK_SYMBOLS (t.ex. OVH) provas Yahoo Finance först,
    sedan Avanza vid misslyckande.

    Raises:
        RuntimeError: Om alla datakällor misslyckas.
    """
    return fetch_stock_data_with_fallback(symbol)


def save_market_data(data: dict):
    """Spara marknadsdata till SQLite"""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        today = datetime.now().strftime("%Y-%m-%d")

        c.execute(
            """
            INSERT OR REPLACE INTO market_data
            (date, symbol, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                today,
                data["symbol"],
                data["timestamp"],
                data["open"],
                data["high"],
                data["low"],
                data["price"],
                data["volume"],
            ),
        )

        conn.commit()
    finally:
        conn.close()


# === TRIGGER-UTVÄRDERING ===
def create_triggers():
    """Skapa dagens triggers"""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Kolla om triggers redan finns för idag
        c.execute("SELECT COUNT(*) FROM triggers WHERE date = ?", (today,))
        count = c.fetchone()[0]

        if count > 0:
            logger.info("%s triggers already exist for %s, skipping creation", count, today)
            return

        triggers = [
            (today, "NVDA", "Open_Above", "price > open", "premarket_report"),
            (today, "WMT", "Open_Above", "price > open", "premarket_report"),
            (today, "TTWO", "Premarket_Break", "bryter premarket-high/low", "premarket_report"),
            (today, "WDAY", "Gap_Defense", "rapportgapet försvaras", "premarket_report"),
            (today, "ENPH", "Momentum", "momentum kvar efter uppgradering", "premarket_report"),
            (today, "OVH", "Momentum", "molntjänster accelererar i Europa", "premarket_report"),
            (today, "ASML", "Momentum", "lithography demand strong", "premarket_report"),
            (today, "SAP", "Open_Above", "price > open", "premarket_report"),
            (today, "ADYEN", "Momentum", "payments volume growth", "premarket_report"),
            (today, "SIE", "Open_Above", "price > open", "premarket_report"),
        ]

        for t in triggers:
            c.execute(
                """
                INSERT INTO triggers (date, symbol, trigger_type, condition, source)
                VALUES (?, ?, ?, ?, ?)
            """,
                t,
            )

        conn.commit()
        logger.info("%s triggers created for %s", len(triggers), today)
    finally:
        conn.close()


def evaluate_trigger(data: dict, trigger_type: str) -> str:
    """Utvärdera en trigger baserat på aktiedata"""
    if not data:
        return "error"

    price = data["price"]
    open_price = data["open"]
    change_pct = data["change_pct"]

    if trigger_type == "Open_Above":
        return "hit" if price > open_price else "miss"

    elif trigger_type == "Premarket_Break":
        # Stor rörelse i första timmen
        return "hit" if abs(change_pct) > 3 else "miss"

    elif trigger_type == "Gap_Defense":
        # Positiv förändring = gap försvaras
        return "hit" if change_pct > 0 else "miss"

    elif trigger_type == "Momentum":
        # Uppgradering + positiv rörelse = hit
        return "hit" if change_pct > 0 else "miss"

    return "unknown"


def update_trigger_stats(symbol: str, trigger_type: str, result: str, change_pct: float):
    """Uppdatera historisk statistik"""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        c.execute(
            """
            INSERT INTO trigger_stats (symbol, trigger_type, total_evaluated, hits, misses, hit_rate)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(symbol, trigger_type) DO UPDATE SET
                total_evaluated = total_evaluated + 1,
                hits = CASE WHEN ? = 'hit' THEN hits + 1 ELSE hits END,
                misses = CASE WHEN ? = 'miss' THEN misses + 1 ELSE misses END,
                hit_rate = ROUND(
                    CAST(hits + CASE WHEN ? = 'hit' THEN 1 ELSE 0 END AS REAL)
                    / (total_evaluated + 1) * 100, 2
                ),
                last_updated = CURRENT_TIMESTAMP
        """,
            (
                symbol,
                trigger_type,
                1 if result == "hit" else 0,
                1 if result == "miss" else 0,
                100.0 if result == "hit" else 0.0,
                result,
                result,
                result,
            ),
        )

        conn.commit()
    finally:
        conn.close()


def get_trigger_accuracy(symbol: str, trigger_type: str) -> float:
    """Hämta N1: trigger-träffsäkerhet (0.0-1.0) från trigger_stats.

    Returnerar hit_rate / 100, eller 0.5 om ingen data finns.
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT hit_rate, total_evaluated, hits, misses
            FROM trigger_stats
            WHERE symbol = ? AND trigger_type = ?
        """,
            (symbol, trigger_type),
        )
        row = c.fetchone()
        if row is None:
            return 0.5  # Default: 50% när ingen data finns
        hit_rate, total, hits, misses = row
        if total is None or total == 0:
            return 0.5
        return round(min(1.0, max(0.0, hit_rate / 100)), 4)
    finally:
        conn.close()


def get_sector_correlation_accuracy(symbol: str) -> float:
    """Hämta N2: sektor-korrelationsaccuracy (0.0-1.0).

    Läser från backtest_sector_analysis. Returnerar 0.5 om ingen data finns.
    """

    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Räkna hur ofta sektorkorrelationen var korrekt
        c.execute(
            """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN sector_correlated = 1 THEN 1 ELSE 0 END) as correlated
            FROM backtest_sector_analysis
            WHERE symbol = ?
        """,
            (symbol,),
        )
        row = c.fetchone()
        if row is None or row[0] == 0:
            return 0.5  # Default: 50% när ingen data finns
        total, correlated = row
        if total == 0:
            return 0.5
        return round(min(1.0, max(0.0, correlated / total)), 4)
    except sqlite3.OperationalError:
        return 0.5
    finally:
        conn.close()


def get_historical_combined_accuracy(symbol: str) -> float:
    """Hämta historisk kombinerad accuracy från evaluations.

    Returnerar andelen "hit" över alla utvärderingar för symbolen.
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN e.result = 'hit' THEN 1 ELSE 0 END) as hits
            FROM evaluations e
            JOIN triggers t ON e.trigger_id = t.id
            WHERE t.symbol = ?
        """,
            (symbol,),
        )
        row = c.fetchone()
        if row is None or row[0] == 0:
            return 0.5  # Default: 50% när ingen data finns
        total, hits = row
        if total == 0:
            return 0.5
        return round(min(1.0, max(0.0, hits / total)), 4)
    finally:
        conn.close()


def determine_direction(trigger_type: str, condition: str, result: str) -> str:
    """Bestäm riktning (bullish/bearish/neutral) för en trigger.

    Använder sektoranalysens extract_direction som fallback.
    """
    # Först: utled från trigger_type
    trigger_type_lower = trigger_type.lower()
    bullish_types = {"open_above", "gap_defense", "momentum"}
    if any(bt in trigger_type_lower for bt in bullish_types):
        return "bullish"

    bearish_types = {"open_below", "breakdown", "weakness"}
    if any(bt in trigger_type_lower for bt in bearish_types):
        return "bearish"

    # Fallback: från condition-text
    from sector_analysis import extract_direction

    direction = extract_direction(condition)

    # Om trigger slog igenom (hit) men direction är neutral, gissa bullish för positiva triggers
    if direction == "neutral" and result == "hit":
        return "bullish"

    return direction


def save_signal(signal: dict, date: str, evaluation_time: str, price_data: dict):
    """Spara en signal till databasen."""
    if signal is None:
        return

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT OR REPLACE INTO signals
            (date, evaluation_time, symbol, trigger_type, trigger_result,
             signal_type, direction, strength, confidence_score, recommendation,
             price_at_eval, open_price, change_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                date,
                evaluation_time,
                signal["symbol"],
                signal.get("trigger_type", ""),
                "hit" if signal.get("trigger_result") else "miss",
                signal["signal"],
                signal["direction"],
                signal["strength"],
                signal["confidence_score"],
                signal["recommendation"],
                price_data.get("price"),
                price_data.get("open"),
                price_data.get("change_pct"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def generate_signals_for_result(result: dict, evaluation_time: str) -> dict | None:
    """Generera signal för ett specifikt utvärderingsresultat.

    Beräknar confidence score från N1, N2 och historisk accuracy,
    genererar köp/sälj-signal om styrka >= 2.
    """
    symbol = result["symbol"]
    trigger_type = result["trigger_type"]
    trigger_result = result["result"] == "hit"
    condition = result.get("condition", "")

    # Bestäm riktning
    direction = determine_direction(trigger_type, condition, result["result"])

    if direction not in ("bullish", "bearish"):
        return None

    # Beräkna N1, N2 och historisk accuracy
    n1 = get_trigger_accuracy(symbol, trigger_type)
    n2 = get_sector_correlation_accuracy(symbol)
    historical = get_historical_combined_accuracy(symbol)

    confidence = calculate_confidence_score(n1, n2, historical)

    # Generera signal (returnerar None om styrka < 2)
    signal = generate_signal(symbol, direction, confidence, trigger_result=trigger_result)
    if signal is not None:
        signal["trigger_type"] = trigger_type
        signal["n1"] = n1
        signal["n2"] = n2
        signal["historical"] = historical

    return signal


def evaluate_all_triggers(evaluation_time: str = "1h"):
    """Hämta alla aktiva triggers och utvärdera dem"""
    valid_times = {"1h", "2h", "EOD"}
    if evaluation_time not in valid_times:
        logger.error("Invalid evaluation_time: %s. Must be: %s", evaluation_time, valid_times)
        return []

    conn = get_db_connection()
    c = conn.cursor()

    try:
        today = datetime.now().strftime("%Y-%m-%d")

        c.execute(
            """
            SELECT id, symbol, trigger_type, condition
            FROM triggers
            WHERE date = ? AND status = 'active'
        """,
            (today,),
        )

        triggers = c.fetchall()
    finally:
        conn.close()

    results = []
    signals = []

    for trigger in triggers:
        trigger_id, symbol, trigger_type, condition = trigger

        logger.info("Evaluating %s (%s) for %s", symbol, trigger_type, evaluation_time)
        try:
            data = fetch_stock_data(symbol)
        except Exception as e:
            logger.error("Could not fetch data for %s: %s", symbol, e)
            continue

        save_market_data(data)
        result = evaluate_trigger(data, trigger_type)

        # Spara utvärdering — idempotent via INSERT OR REPLACE (UNIQUE constraint)
        conn2 = get_db_connection()
        c2 = conn2.cursor()
        try:
            c2.execute(
                """
                INSERT OR REPLACE INTO evaluations
                (trigger_id, evaluation_time, price_at_eval, open_price, result, evaluated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (trigger_id, evaluation_time, data["price"], data["open"], result),
            )
            conn2.commit()
        finally:
            conn2.close()

        # Uppdatera statistik (bara vid första utvärderingen?)
        # Vi vill inte räkna samma trigger flera gånger för olika tider
        # Så vi uppdaterar statistik oavsett — det är total_evaluated som gäller
        update_trigger_stats(symbol, trigger_type, result, data["change_pct"])

        result_dict = {
            "symbol": symbol,
            "trigger_type": trigger_type,
            "condition": condition,
            "open": data["open"],
            "price": data["price"],
            "change_pct": data["change_pct"],
            "result": result,
            "volume": data["volume"],
            "evaluation_time": evaluation_time,
        }
        results.append(result_dict)

        # Generera signal
        signal = generate_signals_for_result(result_dict, evaluation_time)
        if signal is not None:
            save_signal(signal, today, evaluation_time, result_dict)
            signals.append(signal)
            logger.info(
                "Signal: %s (confidence: %s)", signal["recommendation"], signal["confidence_score"]
            )

        logger.info(
            "Result: %s %s (price: $%s, open: $%s)", symbol, result, data["price"], data["open"]
        )

    return results, signals


# === DISCORD ===
async def send_discord_report(results: list[dict], evaluation_time: str = "1h", signals: list[dict] = None):
    """Skicka trigger-rapport till Discord"""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("No DISCORD_WEBHOOK_URL set — skipping Discord report")
        return

    if not results:
        logger.warning("No results to report")
        return

    if not discord_circuit_breaker.can_execute():
        logger.error("Discord webhook blocked by circuit breaker")
        return

    hits = sum(1 for r in results if r["result"] == "hit")
    misses = sum(1 for r in results if r["result"] == "miss")

    # Tid-etikett för Discord
    time_labels = {"1h": "1h (16:35 CET)", "2h": "2h (18:35 CET)", "EOD": "EOD (23:00 CET)"}
    time_label = time_labels.get(evaluation_time, evaluation_time)

    # Bygg Discord-embed
    fields = []
    for r in results:
        emoji = "✅" if r["result"] == "hit" else "❌"
        color_icon = "🟢" if r["change_pct"] > 0 else "🔴"
        fields.append(
            {
                "name": f"{emoji} {r['symbol']} ({r['trigger_type']})",
                "value": f"{color_icon} ${r['open']} → ${r['price']} ({r['change_pct']:+.2f}%)",
                "inline": True,
            }
        )

    fields.append(
        {
            "name": "📈 Sammanfattning",
            "value": (
                f"**{hits}** träff, **{misses}** miss "
                f"(**{hits}/{len(results)}** = {hits / len(results) * 100:.0f}%)"
            ),
            "inline": False,
        }
    )

    # Lägg till signaler om det finns några
    if signals:
        buy_signals = [s for s in signals if s["signal"] == "buy"]
        sell_signals = [s for s in signals if s["signal"] == "sell"]

        if buy_signals:
            buy_lines = []
            for s in buy_signals:
                stars = "⭐" * s["strength"]
                buy_lines.append(f"🟢 {s['symbol']} {stars} (confidence: {s['confidence_score']:.2f})")
            fields.append(
                {"name": f"📗 Köpsignaler ({len(buy_signals)})", "value": "\n".join(buy_lines), "inline": False}
            )

        if sell_signals:
            sell_lines = []
            for s in sell_signals:
                stars = "⭐" * s["strength"]
                sell_lines.append(f"🔴 {s['symbol']} {stars} (confidence: {s['confidence_score']:.2f})")
            fields.append(
                {"name": f"📕 Säljsignaler ({len(sell_signals)})", "value": "\n".join(sell_lines), "inline": False}
            )

    embed = {
        "title": f"📊 Trigger-rapport: {datetime.now().strftime('%Y-%m-%d')} — {time_label}",
        "color": 0x00FF00 if hits >= misses else 0xFF0000,
        "fields": fields,
        "footer": {"text": "Valvet Trading Triggers 🤖📈"},
    }

    payload = {"embeds": [embed]}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                if resp.status == 204:
                    discord_circuit_breaker.record_success()
                    logger.info("Discord report sent")
                else:
                    discord_circuit_breaker.record_failure()
                    logger.error("Discord error: HTTP %s", resp.status)
        except aiohttp.ClientError as exc:
            discord_circuit_breaker.record_failure()
            logger.error("Discord connection error: %s", exc)


# === RAPPORTERING ===
def print_results(results: list[dict], evaluation_time: str = "1h", signals: list[dict] = None):
    """Skriv ut resultat i terminalen"""
    time_labels = {"1h": "1h-utvärdering", "2h": "2h-utvärdering", "EOD": "EOD-utvärdering"}
    time_label = time_labels.get(evaluation_time, evaluation_time)

    print("\n" + "=" * 70)
    print(f"📊 TRIGGER-RAPPORT ({time_label}): {datetime.now().strftime('%Y-%m-%d %H:%M CET')}")
    print("=" * 70)

    print(f"\n{'Aktie':<8} {'Trigger':<18} {'Öppning':<12} {'Pris':<12} {'Förändring':<12} {'Resultat':<10}")
    print("-" * 70)

    for r in results:
        emoji = "✅" if r["result"] == "hit" else "❌"
        change_str = f"{r['change_pct']:+.2f}%"
        print(
            f"{r['symbol']:<8} {r['trigger_type']:<18} "
            f"${r['open']:<11.2f} ${r['price']:<11.2f} "
            f"{change_str:<12} {emoji} {r['result']}"
        )

    hits = sum(1 for r in results if r["result"] == "hit")
    print(f"\n{'=' * 70}")
    print(f"Sammanfattning: {hits}/{len(results)} träffar ({hits / len(results) * 100:.0f}%)")

    # Skriv ut signaler
    if signals:
        print(f"\n{'=' * 70}")
        print("📶 SIGNALER")
        print("=" * 70)
        for s in signals:
            sig_emoji = "🟢" if s["signal"] == "buy" else "🔴"
            stars = "⭐" * s["strength"]
            print(f"{sig_emoji} {s['recommendation']} {stars} (confidence: {s['confidence_score']:.4f})")
            print(f"   N1={s.get('n1', 'N/A'):.2f}, N2={s.get('n2', 'N/A'):.2f}, hist={s.get('historical', 'N/A'):.2f}")
        print("=" * 70)

    print("=" * 70 + "\n")


def get_historical_accuracy(symbol: str = None, days: int = 30) -> list[dict]:
    """Hämta historisk träffsäkerhet"""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        if symbol:
            c.execute(
                """
                SELECT symbol, trigger_type, total_evaluated, hits, misses, hit_rate
                FROM trigger_stats
                WHERE symbol = ?
                ORDER BY hit_rate DESC
            """,
                (symbol,),
            )
        else:
            c.execute("""
                SELECT symbol, trigger_type, total_evaluated, hits, misses, hit_rate
                FROM trigger_stats
                ORDER BY hit_rate DESC
            """)

        rows = c.fetchall()
        return [
            {
                "symbol": row[0],
                "trigger_type": row[1],
                "total": row[2],
                "hits": row[3],
                "misses": row[4],
                "hit_rate": row[5],
            }
            for row in rows
        ]
    finally:
        conn.close()


def print_historical_stats():
    """Skriv ut historisk statistik"""
    stats = get_historical_accuracy()

    if not stats:
        logger.info("No historical data yet")
        return

    print("\n" + "=" * 70)
    print("📊 HISTORISK TRÄFFSÄKERHET")
    print("=" * 70)
    print(f"\n{'Aktie':<8} {'Trigger':<18} {'Totalt':<8} {'Träff':<8} {'Miss':<8} {'Rate':<8}")
    print("-" * 70)

    for s in stats:
        print(
            f"{s['symbol']:<8} {s['trigger_type']:<18} "
            f"{s['total']:<8} {s['hits']:<8} {s['misses']:<8} "
            f"{s['hit_rate']:<7.1f}%"
        )

    print("=" * 70 + "\n")


# === HUVUDPROGRAM ===
async def main():
    evaluation_time = os.environ.get("EVALUATION_TIME", "1h")
    if len(sys.argv) > 1:
        evaluation_time = sys.argv[1]

    time_labels = {"1h": "1h (16:35 CET)", "2h": "2h (18:35 CET)", "EOD": "EOD (23:00 CET)"}
    time_label = time_labels.get(evaluation_time, evaluation_time)

    logger.info("Trading Trigger System V1 — %s", time_label)

    init_db()
    create_triggers()

    logger.info("Fetching stock data and evaluating triggers (%s)...", evaluation_time)
    results, signals = evaluate_all_triggers(evaluation_time=evaluation_time)

    print_results(results, evaluation_time=evaluation_time, signals=signals)
    print_historical_stats()

    await send_discord_report(results, evaluation_time=evaluation_time, signals=signals)

    logger.info("Done")


if __name__ == "__main__":
    asyncio.run(main())
