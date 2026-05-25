"""
Sektorkorrelationsanalys för Trading Triggers.

Extraherar bullish/bearish-riktning från trigger-text och
utvärderar om triggers korrelerar med sektormomentum.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd
import yfinance as yf

from resilience import retry_yfinance

DB_PATH = Path("data/triggers.db")


# === SEKTORMAPPNING ===
# Utbyggbar: lägg till nya aktier/sektorer enkelt
SECTOR_MAP: dict[str, str] = {
    # Semiconductor
    "NVDA": "SOXX",
    "AMD": "SOXX",
    "ARM": "SOXX",
    "INTC": "SOXX",
    "QCOM": "SOXX",
    "AVGO": "SOXX",
    "TSM": "SOXX",
    "MU": "SOXX",
    "LRCX": "SOXX",
    "KLAC": "SOXX",
    # Consumer Discretionary
    "TGT": "XLY",
    "WMT": "XLY",
    "COST": "XLY",
    "AMZN": "XLY",
    "HD": "XLY",
    "LOW": "XLY",
    "NKE": "XLY",
    "MCD": "XLY",
    "SBUX": "XLY",
    "TJX": "XLY",
    # Home Construction
    "DHI": "ITB",
    "LEN": "ITB",
    "PHM": "ITB",
    "TOL": "ITB",
    "NVR": "ITB",
    # Technology / Communication Services
    "WDAY": "XLK",
    "CRM": "XLK",
    "MSFT": "XLK",
    "AAPL": "XLK",
    "GOOGL": "XLK",
    "META": "XLK",
    "TTWO": "XLC",
    "NFLX": "XLC",
    "DIS": "XLC",
    "CMCSA": "XLC",
    # Clean Energy
    "ENPH": "ICLN",
    "SEDG": "ICLN",
    "FSLR": "ICLN",
    "CSIQ": "ICLN",
    "SPWR": "ICLN",
    "RUN": "ICLN",
    "BE": "ICLN",
    # Cloud / Software
    "NOW": "SKYY",
    "SNOW": "SKYY",
    "NET": "SKYY",
    "DDOG": "SKYY",
    # Cybersecurity
    "CRWD": "HACK",
    "PANW": "HACK",
    "FTNT": "HACK",
    "CYBR": "HACK",
    # Cloud / Hosting (European)
    "OVH": "SKYY",
    # Fintech
    "SQ": "FINX",
    "PYPL": "FINX",
    "UPST": "FINX",
    "SOFI": "FINX",
    # Biotech
    "BIIB": "XBI",
    "GILD": "XBI",
    "REGN": "XBI",
    "VRTX": "XBI",
    # Gaming
    "ATVI": "BJK",
    "EA": "BJK",
    "DKNG": "BJK",
    # Networking / CDN
    "AKAM": "FXL",
    "F5": "FXL",
    "LLNW": "FXL",
    # Retail
    "BBY": "XRT",
    "DKS": "XRT",
    "ROST": "XRT",
    "ULTA": "XRT",
}

# ETF-metadata (för framtida utökning)
ETF_INFO: dict[str, dict[str, str]] = {
    "SOXX": {"name": "iShares Semiconductor ETF", "category": "Technology"},
    "XLY": {
        "name": "Consumer Discretionary Select Sector SPDR",
        "category": "Consumer",
    },
    "ITB": {"name": "iShares U.S. Home Construction ETF", "category": "Real Estate"},
    "XHB": {"name": "SPDR S&P Homebuilders ETF", "category": "Real Estate"},
    "XLK": {"name": "Technology Select Sector SPDR", "category": "Technology"},
    "XLC": {
        "name": "Communication Services Select Sector SPDR",
        "category": "Communication",
    },
    "ICLN": {"name": "iShares Global Clean Energy ETF", "category": "Energy"},
    "QCLN": {
        "name": "First Trust NASDAQ Clean Edge Green Energy",
        "category": "Energy",
    },
    "SKYY": {"name": "First Trust Cloud Computing ETF", "category": "Technology"},
    "HACK": {"name": "ETFMG Prime Cyber Security ETF", "category": "Technology"},
    "FINX": {"name": "Global X FinTech ETF", "category": "Financials"},
    "XBI": {"name": "SPDR S&P Biotech ETF", "category": "Healthcare"},
    "BJK": {"name": "VanEck Gaming ETF", "category": "Consumer"},
    "FXL": {"name": "First Trust Technology AlphaDEX", "category": "Technology"},
    "XRT": {"name": "SPDR S&P Retail ETF", "category": "Consumer"},
}


# === BULLISH/BEARISH NYCKELORD ===
BULLISH_KEYWORDS: set[str] = {
    "momentum",
    "accelerera",
    "accelererar",
    "stiga",
    "stiger",
    "över",
    "konstruktiv",
    "stärker",
    "stärka",
    "krysst köp",
    "återhämtning",
    "återhämta",
    "uppsida",
    "breakout",
    "break",
    "higher",
    "rally",
    "bounce",
    "recover",
    "recovery",
    "bullish",
    "buy",
    "long",
    "strength",
    "strong",
    "stark",
    "starkt",
    "starkare",
    "lyfter",
    "lyft",
    "efterfrågan",
    "support",
    "hållbar",
    "positiv",
    "öka",
    "ökning",
    "tillväxt",
    "growth",
    "expansion",
    "övertala",
    "övertygad",
    "övergå",
    "passera",
    "överskrida",
    "överträffa",
    "outperform",
    "beat",
    "beaten",
    "rebound",
    "uptrend",
    "klättra",
    "climb",
    "surge",
    "spike",
    "gap up",
    "högre",
    "high",
    "top",
    "peak",
    "resistance",
}

BEARISH_KEYWORDS: set[str] = {
    "nedställ",
    "nedgång",
    "svaghet",
    "svag",
    "under",
    "falla",
    "faller",
    "sälja",
    "sell",
    "risk",
    "varning",
    "warning",
    "nedåt",
    "downside",
    "breakdown",
    "lower",
    "drop",
    "decline",
    "slide",
    "tumble",
    "crash",
    "bearish",
    "short",
    "weakness",
    "weak",
    "resistance",
    "negativ",
    "minska",
    "minskning",
    "fallande",
    "falling",
    "downtrend",
    "sjunka",
    "sink",
    "plunge",
    "collapse",
    "dump",
    "gap down",
    "låg",
    "low",
    "bottom",
    "support",
    "cut",
    "reduce",
    "downgrade",
    "nedgradering",
    "concern",
    "oro",
    "worried",
    "worrisome",
    "cautious",
    "försiktig",
    "försiktighet",
    "correction",
    "korrektion",
    "pullback",
    "retracement",
}

# Nyckelord som har kontextberoende betydelse (hanteras speciellt)
CONTEXT_DEPENDENT: dict[str, tuple[set[str], set[str]]] = {
    "resistance": (
        {"över", "bryter", "break", "överskrida", "passera", "above"},
        {"vid", "stannar", "under", "below", "nära", "close to"},
    ),
    "support": (
        {"vid", "håller", "hold", "stannar", "stays", "bounces", "bounce"},
        {"faller", "under", "below", "break", "bryter", "tappar", "loses"},
    ),
}


def _count_keywords(text: str, keywords: list) -> int:
    """Räkna antal matchande nyckelord i text.

    Används av extract_direction för att räkna bullish/bearish ord.
    Hanterar både enskilda ord och ordgrupper.
    """
    text_lower = text.lower()
    individual_words = re.findall(r"[a-zA-ZåäöÅÄÖ]+", text_lower)
    word_set = set(individual_words)

    count = 0
    for keyword in keywords:
        if " " in keyword:
            if keyword in text_lower:
                count += 1
        else:
            if keyword in word_set:
                count += 1
    return count


def extract_direction(trigger_text: str) -> str:
    """Analysera trigger-text och returnera riktning: bullish, bearish eller neutral.

    Använder regelbaserad nyckelords-matchning med kontextberoende hantering.
    Om både bullish och bearish ord finns, räknas antal förekomster.
    """
    if not trigger_text or not isinstance(trigger_text, str):
        return "neutral"

    text_lower = trigger_text.lower()

    bullish_count = _count_keywords(trigger_text, BULLISH_KEYWORDS)
    bearish_count = _count_keywords(trigger_text, BEARISH_KEYWORDS)

    # Kontextberoende ord
    for keyword, (bullish_context, bearish_context) in CONTEXT_DEPENDENT.items():
        if keyword in text_lower:
            idx = text_lower.find(keyword)
            if idx != -1:
                context_window = text_lower[max(0, idx - 40) : min(len(text_lower), idx + 40)]
                for ctx in bullish_context:
                    if ctx in context_window:
                        bullish_count += 1
                for ctx in bearish_context:
                    if ctx in context_window:
                        bearish_count += 1

    # Specifika mönster
    if re.search(r"återtar\s+\$", text_lower):
        bullish_count += 1

    if re.search(r"svaghet\s+under\s+\$", text_lower):
        bearish_count += 1

    if "mer nedställ" in text_lower or "mer nedgång" in text_lower:
        bearish_count += 1

    if re.search(r"(?:momentum|moment)\s+(?:accelerera|accelererar|öka)", text_lower):
        bullish_count += 1

    if bullish_count > bearish_count:
        return "bullish"
    elif bearish_count > bullish_count:
        return "bearish"
    else:
        return "neutral"


def get_sector_etf(symbol: str) -> str:
    """Mappa aktiesymbol till sektor-ETF.

    Returnerar ETF-ticker eller tom sträng om ingen matchning hittas.
    """
    if not symbol:
        return ""
    return SECTOR_MAP.get(symbol.upper(), "")


@retry_yfinance
def fetch_sector_data(etf_symbol: str, target_date: str) -> dict:
    """Hämta daglig OHLC-data för en sektor-ETF från yfinance.

    Args:
        etf_symbol: ETF-ticker, t.ex. "SOXX"
        target_date: Datum i format "YYYY-MM-DD"

    Returns:
        dict med open, close, change_percent eller tom dict vid fel.
    """
    if not etf_symbol:
        return {}

    try:
        ticker = yf.Ticker(etf_symbol)
        start = pd.Timestamp(target_date) - pd.Timedelta(days=5)
        end = pd.Timestamp(target_date) + pd.Timedelta(days=2)
        hist = ticker.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
        )
    except Exception:
        return {}

    if hist is None or hist.empty:
        return {}

    hist = hist.reset_index()
    hist["Date"] = pd.to_datetime(hist["Date"]).dt.tz_localize(None)

    target = pd.Timestamp(target_date)
    row = hist[hist["Date"] == target]

    if row.empty:
        return {}

    row = row.iloc[0]
    open_price = float(row["Open"])
    close_price = float(row["Close"])
    change_pct = round((close_price - open_price) / open_price * 100, 2) if open_price != 0 else 0.0

    return {
        "symbol": etf_symbol,
        "date": target_date,
        "open": round(open_price, 2),
        "close": round(close_price, 2),
        "change_percent": change_pct,
        "high": round(float(row["High"]), 2),
        "low": round(float(row["Low"]), 2),
        "volume": int(row["Volume"]),
    }


def evaluate_sector_correlation(
    trigger_result: bool,
    direction: str,
    sector_change_percent: float,
) -> bool:
    """Utvärdera om trigger korrelerar med sektormomentum.

    Args:
        trigger_result: True = trigger slog igenom (HIT), False = miss
        direction: "bullish" eller "bearish"
        sector_change_percent: Sektorns dagliga förändring i procent

    Returns:
        True om korrelationen är korrekt, False annars.
    """
    if direction not in ("bullish", "bearish"):
        return False

    if trigger_result:
        if direction == "bullish":
            return sector_change_percent > 0
        else:
            return sector_change_percent < 0
    else:
        if direction == "bullish":
            return sector_change_percent < 0
        else:
            return sector_change_percent > 0


def analyze_backtest_sector_correlation(backtest_results: list) -> dict:
    """Analysera sektorkorrelation för en lista med backtest-resultat.

    Args:
        backtest_results: Lista med dicts som innehåller trigger_text och result

    Returns:
        dict med sammanfattning av sektorkorrelation.
    """
    if not backtest_results:
        return {
            "total_backtests": 0,
            "sector_correlated": 0,
            "sector_accuracy": 0.0,
            "per_sector": {},
        }

    total = 0
    correlated = 0
    per_sector: dict[str, dict] = {}

    for res in backtest_results:
        symbol = res.get("symbol", "")
        trigger_text = res.get("condition", "") or res.get("trigger_text", "")
        trigger_result = res.get("result") == "hit"
        target_date = res.get("target_date", "")

        direction = extract_direction(trigger_text)
        etf = get_sector_etf(symbol)

        if not etf or direction == "neutral" or not target_date:
            continue

        sector_data = res.get("sector_data")
        if sector_data is None:
            sector_data = fetch_sector_data(etf, target_date)

        if not sector_data:
            continue

        sector_change = sector_data.get("change_percent", 0.0)
        is_correct = evaluate_sector_correlation(trigger_result, direction, sector_change)

        total += 1
        if is_correct:
            correlated += 1

        if etf not in per_sector:
            per_sector[etf] = {
                "total": 0,
                "correlated": 0,
                "bullish_total": 0,
                "bullish_correct": 0,
                "bearish_total": 0,
                "bearish_correct": 0,
                "symbols": set(),
            }

        per_sector[etf]["total"] += 1
        per_sector[etf]["symbols"].add(symbol)
        if is_correct:
            per_sector[etf]["correlated"] += 1

        if direction == "bullish":
            per_sector[etf]["bullish_total"] += 1
            if is_correct:
                per_sector[etf]["bullish_correct"] += 1
        else:
            per_sector[etf]["bearish_total"] += 1
            if is_correct:
                per_sector[etf]["bearish_correct"] += 1

    for etf in per_sector:
        stats = per_sector[etf]
        stats["accuracy"] = round(stats["correlated"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0.0
        stats["bullish_accuracy"] = (
            round(stats["bullish_correct"] / stats["bullish_total"] * 100, 1) if stats["bullish_total"] > 0 else 0.0
        )
        stats["bearish_accuracy"] = (
            round(stats["bearish_correct"] / stats["bearish_total"] * 100, 1) if stats["bearish_total"] > 0 else 0.0
        )
        stats["symbols"] = sorted(list(stats["symbols"]))

    sector_accuracy = round(correlated / total * 100, 1) if total > 0 else 0.0

    return {
        "total_backtests": total,
        "sector_correlated": correlated,
        "sector_accuracy": sector_accuracy,
        "per_sector": per_sector,
    }


# === DATABAS-FUNKTIONER ===


def init_sector_analysis_tables() -> None:
    """Skapa tabeller för sektorkorrelationsanalys."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest_sector_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backtest_result_id INTEGER,
            symbol TEXT NOT NULL,
            target_date TEXT NOT NULL,
            evaluation_time TEXT NOT NULL,
            direction TEXT NOT NULL,
            sector_etf TEXT NOT NULL,
            sector_change_percent REAL,
            sector_correlated INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(backtest_result_id, symbol, target_date, evaluation_time),
            FOREIGN KEY (backtest_result_id) REFERENCES backtest_results(id)
        )
        """
    )

    conn.commit()
    conn.close()
    print("✅ Sektoranalystabeller initierade")


def save_sector_analysis(
    backtest_result_id: int,
    symbol: str,
    target_date: str,
    evaluation_time: str,
    direction: str,
    sector_etf: str,
    sector_change_percent: float,
    sector_correlated: bool,
) -> None:
    """Spara sektoranalys för ett specifikt backtest-resultat."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    c = conn.cursor()

    c.execute(
        """
        INSERT OR REPLACE INTO backtest_sector_analysis
        (backtest_result_id, symbol, target_date, evaluation_time,
         direction, sector_etf, sector_change_percent, sector_correlated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            backtest_result_id,
            symbol,
            target_date,
            evaluation_time,
            direction,
            sector_etf,
            sector_change_percent,
            1 if sector_correlated else 0,
        ),
    )

    conn.commit()
    conn.close()


def load_sector_analyses(
    target_date: str | None = None,
    symbol: str | None = None,
) -> list[dict]:
    """Ladda sparade sektoranalyser från databasen."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    c = conn.cursor()

    query = """
        SELECT backtest_result_id, symbol, target_date, evaluation_time,
               direction, sector_etf, sector_change_percent, sector_correlated
        FROM backtest_sector_analysis
        WHERE 1=1
    """
    params: list = []

    if target_date:
        query += " AND target_date = ?"
        params.append(target_date)
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper())

    query += " ORDER BY target_date DESC, symbol, evaluation_time"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    return [
        {
            "backtest_result_id": row[0],
            "symbol": row[1],
            "target_date": row[2],
            "evaluation_time": row[3],
            "direction": row[4],
            "sector_etf": row[5],
            "sector_change_percent": row[6],
            "sector_correlated": bool(row[7]),
        }
        for row in rows
    ]


if __name__ == "__main__":
    # Snabb test
    test_texts = [
        "NVDA – om aktien återtar $225 kan momentum accelerera",
        "AKAM – fortsatt svaghet under $140 kan ge mer nedställ",
        "WMT – rapportgapet försvaras vid $98",
        "TTWO – stark efterfrågan lyfter aktien",
        "ENPH – osäkerhet kring solcellspolitik",
    ]

    print("=== Direction-extraktionstest ===")
    for text in test_texts:
        direction = extract_direction(text)
        print(f"  [{direction:8}] {text[:60]}...")

    print("\n=== ETF-mappningstest ===")
    for sym in ["NVDA", "WMT", "TTWO", "WDAY", "ENPH", "UNKNOWN"]:
        etf = get_sector_etf(sym)
        print(f"  {sym:8} → {etf or '(ingen mappning)'}")

    print("\n=== Initiera tabeller ===")
    init_sector_analysis_tables()
