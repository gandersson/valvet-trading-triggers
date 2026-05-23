#!/usr/bin/env python3
"""
PoC: Trading Trigger System
Hämtar kurser, utvärderar triggers, skickar Discord-meddelande.
"""

import asyncio
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional

import yfinance as yf
import aiohttp

# === KONFIGURATION ===
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
STOCKS = ["NVDA", "WMT", "TTWO", "WDAY", "ENPH"]
DB_PATH = "data/triggers.db"

# === DATABAS ===
def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
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
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id INTEGER NOT NULL,
            evaluation_time TEXT NOT NULL,
            price_at_eval REAL,
            open_price REAL,
            result TEXT NOT NULL,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id)
        )
    ''')
    
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
    
    conn.commit()
    conn.close()
    print("✅ Databas initierad")

# === DATAHÄMTNING ===
def fetch_stock_data(symbol: str) -> Optional[Dict]:
    """Hämta aktuell data från Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", interval="1m")
        
        if hist.empty:
            print(f"⚠️  Ingen data för {symbol}")
            return None
        
        # Senaste datapunkt
        latest = hist.iloc[-1]
        # Öppning
        opening = hist.iloc[0]
        
        return {
            "symbol": symbol,
            "price": round(latest["Close"], 2),
            "open": round(opening["Open"], 2),
            "high": round(hist["High"].max(), 2),
            "low": round(hist["Low"].min(), 2),
            "volume": int(latest["Volume"]),
            "change_pct": round((latest["Close"] - opening["Open"]) / opening["Open"] * 100, 2),
            "timestamp": latest.name.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"❌ Fel vid hämtning av {symbol}: {e}")
        return None

def save_market_data(data: Dict):
    """Spara marknadsdata till SQLite"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
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
    conn.close()
    print(f"✅ {len(triggers)} triggers skapade för {today}")

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
        # Simplifierad: kolla om det finns stor rörelse
        return "hit" if abs(change_pct) > 3 else "miss"
    
    elif trigger_type == "Gap_Defense":
        # Simplifierad: positiv förändring = gap försvaras
        return "hit" if change_pct > 0 else "miss"
    
    elif trigger_type == "Momentum":
        # Uppgradering + positiv rörelse = hit
        return "hit" if change_pct > 0 else "miss"
    
    return "unknown"

def evaluate_all_triggers():
    """Hämta alla aktiva triggers och utvärdera dem"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
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
        
        print(f"📊 Utvärderar {symbol} ({trigger_type})...")
        data = fetch_stock_data(symbol)
        
        if data:
            save_market_data(data)
            result = evaluate_trigger(data, trigger_type)
            
            # Separat DB-anslutning för utvärdering
            conn2 = sqlite3.connect(DB_PATH, timeout=10.0)
            c2 = conn2.cursor()
            try:
                c2.execute('''
                    INSERT INTO evaluations 
                    (trigger_id, evaluation_time, price_at_eval, open_price, result)
                    VALUES (?, ?, ?, ?, ?)
                ''', (trigger_id, "1h", data["price"], data["open"], result))
                conn2.commit()
            finally:
                conn2.close()
            
            results.append({
                "symbol": symbol,
                "trigger_type": trigger_type,
                "open": data["open"],
                "price": data["price"],
                "change_pct": data["change_pct"],
                "result": result,
                "volume": data["volume"]
            })
            
            print(f"   Resultat: {result} (pris: ${data['price']}, öppning: ${data['open']})")
        else:
            print(f"   ⚠️  Kunde inte hämta data för {symbol}")
    
    return results

# === DISCORD ===
async def send_discord_report(results: List[Dict]):
    """Skicka trigger-rapport till Discord"""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️  Ingen DISCORD_WEBHOOK_URL satt")
        print("Sätt miljövariabeln: export DISCORD_WEBHOOK_URL=...")
        return
    
    hits = sum(1 for r in results if r["result"] == "hit")
    misses = sum(1 for r in results if r["result"] == "miss")
    
    # Bygg Discord-embed
    embed = {
        "title": f"📊 Trigger-rapport: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "color": 0x00FF00 if hits >= misses else 0xFF0000,
        "fields": []
    }
    
    for r in results:
        emoji = "✅" if r["result"] == "hit" else "❌"
        embed["fields"].append({
            "name": f"{emoji} {r['symbol']} ({r['trigger_type']})",
            "value": f"Öppning: ${r['open']} → Nu: ${r['price']} ({r['change_pct']:+.2f}%)",
            "inline": True
        })
    
    embed["fields"].append({
        "name": "📈 Sammanfattning",
        "value": f"**{hits}** träff, **{misses}** miss ({hits}/{len(results)} = {hits/len(results)*100:.0f}%)",
        "inline": False
    })
    
    payload = {
        "embeds": [embed]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
            if resp.status == 204:
                print("✅ Discord-meddelande skickat!")
            else:
                print(f"❌ Discord-fel: {resp.status}")

# === HUVUDPROGRAM ===
def print_results(results: List[Dict]):
    """Skriv ut resultat i terminalen"""
    print("\n" + "="*60)
    print(f"📊 TRIGGER-RAPPORT: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    
    print(f"\n{'Aktie':<8} {'Trigger':<18} {'Öppning':<10} {'Pris':<10} {'Resultat':<10}")
    print("-"*60)
    
    for r in results:
        emoji = "✅" if r["result"] == "hit" else "❌"
        print(f"{r['symbol']:<8} {r['trigger_type']:<18} ${r['open']:<9.2f} ${r['price']:<9.2f} {emoji} {r['result']}")
    
    hits = sum(1 for r in results if r["result"] == "hit")
    print(f"\n{'='*60}")
    print(f"Sammanfattning: {hits}/{len(results)} träffar ({hits/len(results)*100:.0f}%)")
    print("="*60 + "\n")

async def main():
    print("🚀 Trading Trigger System - PoC")
    print("="*60)
    
    # 1. Initiera databas
    init_db()
    
    # 2. Skapa triggers
    create_triggers()
    
    # 3. Hämta data och utvärdera
    print("\n📥 Hämtar aktiedata och utvärderar triggers...")
    results = evaluate_all_triggers()
    
    # 4. Skriv ut resultat
    print_results(results)
    
    # 5. Skicka till Discord
    await send_discord_report(results)
    
    print("✅ PoC klar!")

if __name__ == "__main__":
    asyncio.run(main())
