#!/usr/bin/env python3
"""
Trading Trigger System - V1
Hämtar kurser, utvärderar triggers, skickar Discord-meddelande.
"""

import asyncio
import sqlite3
import os
import sys
from datetime import datetime
from typing import List, Dict

import yfinance as yf
import aiohttp

from resilience import retry_yfinance, discord_circuit_breaker

# === KONFIGURATION ===
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
STOCKS = ["NVDA", "WMT", "TTWO", "WDAY", "ENPH"]
DB_PATH = "data/triggers.db"

# === DATABAS ===
def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    c = conn.cursor()
    
    # Triggers-tabell
    c.execute('''
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
    ''')
    
    # Utvärderingar — med UNIQUE constraint för idempotens
    c.execute('''
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
    ''')
    
    # Marknadsdata
    c.execute('''
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
    ''')
    
    # Historisk statistik
    c.execute('''
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
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Databas initierad")

def get_db_connection():
    return sqlite3.connect(DB_PATH, timeout=10.0)

# === DATAHÄMTNING ===
@retry_yfinance
def fetch_stock_data(symbol: str) -> Dict:
    """Hämta aktuell data från Yahoo Finance.

    Raises:
        Exception: Om datahämtningen misslyckas efter alla retries.
        ValueError: Om data saknas eller är ofullständig.
    """
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d", interval="1m")

    if hist is None or hist.empty:
        raise ValueError(f"No data returned for {symbol}")

    # Senaste datapunkt
    latest = hist.iloc[-1]
    # Öppning
    opening = hist.iloc[0]

    data = {
        "symbol": symbol,
        "price": round(latest["Close"], 2),
        "open": round(opening["Open"], 2),
        "high": round(hist["High"].max(), 2),
        "low": round(hist["Low"].min(), 2),
        "volume": int(latest["Volume"]),
        "change_pct": round(
            (latest["Close"] - opening["Open"]) / opening["Open"] * 100, 2
        ),
        "timestamp": latest.name.strftime("%Y-%m-%d %H:%M:%S"),
    }

    required_fields = ("symbol", "price", "open", "high", "low", "volume", "change_pct", "timestamp")
    missing = [f for f in required_fields if data.get(f) is None]
    if missing:
        raise ValueError(f"Incomplete data for {symbol}, missing fields: {missing}")

    return data

def save_market_data(data: Dict):
    """Spara marknadsdata till SQLite"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        c.execute('''
            INSERT OR REPLACE INTO market_data 
            (date, symbol, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            today, data["symbol"], data["timestamp"],
            data["open"], data["high"], data["low"],
            data["price"], data["volume"]
        ))
        
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
        c.execute('SELECT COUNT(*) FROM triggers WHERE date = ?', (today,))
        count = c.fetchone()[0]
        
        if count > 0:
            print(f"⚠️  {count} triggers finns redan för {today}, skapar inte nya")
            return
        
        triggers = [
            (today, "NVDA", "Open_Above", "price > open", "premarket_report"),
            (today, "WMT", "Open_Above", "price > open", "premarket_report"),
            (today, "TTWO", "Premarket_Break", "bryter premarket-high/low", "premarket_report"),
            (today, "WDAY", "Gap_Defense", "rapportgapet försvaras", "premarket_report"),
            (today, "ENPH", "Momentum", "momentum kvar efter uppgradering", "premarket_report"),
        ]
        
        for t in triggers:
            c.execute('''
                INSERT INTO triggers (date, symbol, trigger_type, condition, source)
                VALUES (?, ?, ?, ?, ?)
            ''', t)
        
        conn.commit()
        print(f"✅ {len(triggers)} triggers skapade för {today}")
    finally:
        conn.close()

def evaluate_trigger(data: Dict, trigger_type: str) -> str:
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
        c.execute('''
            INSERT INTO trigger_stats (symbol, trigger_type, total_evaluated, hits, misses, hit_rate)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(symbol, trigger_type) DO UPDATE SET
                total_evaluated = total_evaluated + 1,
                hits = CASE WHEN ? = 'hit' THEN hits + 1 ELSE hits END,
                misses = CASE WHEN ? = 'miss' THEN misses + 1 ELSE misses END,
                hit_rate = ROUND(CAST(hits + CASE WHEN ? = 'hit' THEN 1 ELSE 0 END AS REAL) / (total_evaluated + 1) * 100, 2),
                last_updated = CURRENT_TIMESTAMP
        ''', (symbol, trigger_type, 1 if result == "hit" else 0, 1 if result == "miss" else 0, 
              100.0 if result == "hit" else 0.0, result, result, result))
        
        conn.commit()
    finally:
        conn.close()

def evaluate_all_triggers(evaluation_time: str = "1h"):
    """Hämta alla aktiva triggers och utvärdera dem"""
    valid_times = {"1h", "2h", "EOD"}
    if evaluation_time not in valid_times:
        print(f"❌ Ogiltig evaluation_time: {evaluation_time}. Måste vara: {valid_times}")
        return []
    
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        c.execute('''
            SELECT id, symbol, trigger_type, condition 
            FROM triggers 
            WHERE date = ? AND status = 'active'
        ''', (today,))
        
        triggers = c.fetchall()
    finally:
        conn.close()
    
    results = []
    for trigger in triggers:
        trigger_id, symbol, trigger_type, condition = trigger
        
        print(f"📊 Utvärderar {symbol} ({trigger_type}) för {evaluation_time}...")
        try:
            data = fetch_stock_data(symbol)
        except Exception as e:
            print(f"   ❌ Kunde inte hämta data för {symbol}: {e}")
            continue
        
        save_market_data(data)
        result = evaluate_trigger(data, trigger_type)
        
        # Spara utvärdering — idempotent via INSERT OR REPLACE (UNIQUE constraint)
        conn2 = get_db_connection()
        c2 = conn2.cursor()
        try:
            c2.execute('''
                INSERT OR REPLACE INTO evaluations 
                (trigger_id, evaluation_time, price_at_eval, open_price, result, evaluated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (trigger_id, evaluation_time, data["price"], data["open"], result))
            conn2.commit()
        finally:
            conn2.close()
        
        # Uppdatera statistik (bara vid första utvärderingen?)
        # Vi vill inte räkna samma trigger flera gånger för olika tider
        # Så vi uppdaterar statistik oavsett — det är total_evaluated som gäller
        update_trigger_stats(symbol, trigger_type, result, data["change_pct"])
        
        results.append({
            "symbol": symbol,
            "trigger_type": trigger_type,
            "open": data["open"],
            "price": data["price"],
            "change_pct": data["change_pct"],
            "result": result,
            "volume": data["volume"],
            "evaluation_time": evaluation_time
        })
        
        print(f"   Resultat: {result} (pris: ${data['price']}, öppning: ${data['open']})")
    
    return results

# === DISCORD ===
async def send_discord_report(results: List[Dict], evaluation_time: str = "1h"):
    """Skicka trigger-rapport till Discord"""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️  Ingen DISCORD_WEBHOOK_URL satt")
        print("Sätt miljövariabeln: export DISCORD_WEBHOOK_URL=...")
        return

    if not results:
        print("⚠️  Inga resultat att rapportera")
        return

    # Circuit breaker check
    if not discord_circuit_breaker.can_execute():
        print("❌ Discord webhook blocked by circuit breaker.")
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
        fields.append({
            "name": f"{emoji} {r['symbol']} ({r['trigger_type']})",
            "value": f"{color_icon} ${r['open']} → ${r['price']} ({r['change_pct']:+.2f}%)",
            "inline": True
        })

    fields.append({
        "name": "📈 Sammanfattning",
        "value": f"**{hits}** träff, **{misses}** miss (**{hits}/{len(results)}** = {hits/len(results)*100:.0f}%)",
        "inline": False
    })

    embed = {
        "title": f"📊 Trigger-rapport: {datetime.now().strftime('%Y-%m-%d')} — {time_label}",
        "color": 0x00FF00 if hits >= misses else 0xFF0000,
        "fields": fields,
        "footer": {
            "text": "Valvet Trading Triggers 🤖📈"
        }
    }

    payload = {
        "embeds": [embed]
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                if resp.status == 204:
                    discord_circuit_breaker.record_success()
                    print("✅ Discord-meddelande skickat!")
                else:
                    discord_circuit_breaker.record_failure()
                    print(f"❌ Discord-fel: {resp.status}")
        except aiohttp.ClientError as exc:
            discord_circuit_breaker.record_failure()
            print(f"❌ Discord-anslutningsfel: {exc}")
    
# === RAPPORTERING ===
def print_results(results: List[Dict], evaluation_time: str = "1h"):
    """Skriv ut resultat i terminalen"""
    time_labels = {"1h": "1h-utvärdering", "2h": "2h-utvärdering", "EOD": "EOD-utvärdering"}
    time_label = time_labels.get(evaluation_time, evaluation_time)
    
    print("\n" + "="*70)
    print(f"📊 TRIGGER-RAPPORT ({time_label}): {datetime.now().strftime('%Y-%m-%d %H:%M CET')}")
    print("="*70)
    
    print(f"\n{'Aktie':<8} {'Trigger':<18} {'Öppning':<12} {'Pris':<12} {'Förändring':<12} {'Resultat':<10}")
    print("-"*70)
    
    for r in results:
        emoji = "✅" if r["result"] == "hit" else "❌"
        change_str = f"{r['change_pct']:+.2f}%"
        print(f"{r['symbol']:<8} {r['trigger_type']:<18} ${r['open']:<11.2f} ${r['price']:<11.2f} {change_str:<12} {emoji} {r['result']}")
    
    hits = sum(1 for r in results if r["result"] == "hit")
    print(f"\n{'='*70}")
    print(f"Sammanfattning: {hits}/{len(results)} träffar ({hits/len(results)*100:.0f}%)")
    print("="*70 + "\n")

def get_historical_accuracy(symbol: str = None, days: int = 30) -> List[Dict]:
    """Hämta historisk träffsäkerhet"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        if symbol:
            c.execute('''
                SELECT symbol, trigger_type, total_evaluated, hits, misses, hit_rate
                FROM trigger_stats
                WHERE symbol = ?
                ORDER BY hit_rate DESC
            ''', (symbol,))
        else:
            c.execute('''
                SELECT symbol, trigger_type, total_evaluated, hits, misses, hit_rate
                FROM trigger_stats
                ORDER BY hit_rate DESC
            ''')
        
        rows = c.fetchall()
        return [
            {
                "symbol": row[0],
                "trigger_type": row[1],
                "total": row[2],
                "hits": row[3],
                "misses": row[4],
                "hit_rate": row[5]
            }
            for row in rows
        ]
    finally:
        conn.close()

def print_historical_stats():
    """Skriv ut historisk statistik"""
    stats = get_historical_accuracy()
    
    if not stats:
        print("📊 Inga historiska data ännu")
        return
    
    print("\n" + "="*70)
    print("📊 HISTORISK TRÄFFSÄKERHET")
    print("="*70)
    print(f"\n{'Aktie':<8} {'Trigger':<18} {'Totalt':<8} {'Träff':<8} {'Miss':<8} {'Rate':<8}")
    print("-"*70)
    
    for s in stats:
        print(f"{s['symbol']:<8} {s['trigger_type']:<18} {s['total']:<8} {s['hits']:<8} {s['misses']:<8} {s['hit_rate']:<7.1f}%")
    
    print("="*70 + "\n")

# === HUVUDPROGRAM ===
async def main():
    # Läs evaluation_time från miljövariabel eller argument
    evaluation_time = os.environ.get("EVALUATION_TIME", "1h")
    if len(sys.argv) > 1:
        evaluation_time = sys.argv[1]
    
    time_labels = {"1h": "1h (16:35 CET)", "2h": "2h (18:35 CET)", "EOD": "EOD (23:00 CET)"}
    time_label = time_labels.get(evaluation_time, evaluation_time)
    
    print(f"🚀 Trading Trigger System - V1 — {time_label}")
    print("="*70)
    
    # 1. Initiera databas
    init_db()
    
    # 2. Skapa triggers
    create_triggers()
    
    # 3. Hämta data och utvärdera
    print(f"\n📥 Hämtar aktiedata och utvärderar triggers ({evaluation_time})...")
    results = evaluate_all_triggers(evaluation_time=evaluation_time)
    
    # 4. Skriv ut resultat
    print_results(results, evaluation_time=evaluation_time)
    
    # 5. Skriv ut historisk statistik
    print_historical_stats()
    
    # 6. Skicka till Discord
    await send_discord_report(results, evaluation_time=evaluation_time)
    
    print("✅ Klar!")

if __name__ == "__main__":
    asyncio.run(main())
