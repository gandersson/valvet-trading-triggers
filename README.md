# Valvet Trading Triggers 🤖📈

> Automatiserat system för att spåra, utvärdera och rapportera trading-triggers för US-aktier.
> Byggt för att slippa manuellt kolla kurser kl 16:30 varje dag.

---

## Vad gör detta?

**Kort:** Systemet övervakar aktier, utvärderar om trigger-villkor uppfylls, och rapporterar resultat — allt automatiskt.

**Långt:** Varje morgon definieras triggers för intressanta aktier (t.ex. "NVDA ska återta $225 efter öppning"). Systemet:

1. **Hämtar realtidskurser** från Yahoo Finance
2. **Utvärderar triggers** automatiskt efter 1h, 2h och EOD (End of Day)
3. **Mäter sektorkorrelation** — slog trigger igenom? Gick sektorn i rätt riktning?
4. **Sparar historik** i SQLite för att mäta träffsäkerhet över tid
5. **Rapporterar** till Discord med automatiska sammanfattningar
6. **Backtestar** strategier mot historisk data
7. **Exponerar MCP-server** — integrera med AI-assistenter (Claude, Cursor, etc.)

---

## Snabbstart (5 minuter)

### 1. Klona och installera

```bash
git clone https://github.com/gandersson/valvet-trading-triggers.git
cd valvet-trading-triggers

python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Konfigurera Discord-webhook (valfritt)

```bash
# Skapa config/.env från template
cp config/.env.example config/.env

# Redigera config/.env och lägg in din Discord-webhook URL:
# DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### 3. Kör systemet

```bash
# Manuell körning (testa direkt)
python src/trigger_system_v1.py

# Med Discord-notifiering
./run_with_webhook.sh

# Backtesting
python src/backtest.py --days 30 --symbols NVDA,WMT,TTWO

# MCP-server (för AI-integration)
python src/mcp_server.py
```

### 4. Automatisk schemaläggning (macOS)

```bash
# Kopiera LaunchAgent för automatisk körning vardagar 16:35, 18:35, 23:00
cp com.valvet.trading-triggers.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.valvet.trading-triggers.plist
```

---

## Användning — Steg för steg

### Dagligt flöde (automatiskt)

1. **Morgon:** Triggers definieras i förbörsrapporten (manuellt eller via AI)
2. **16:35 CET (10:35 EST):** 1h-utvärdering — hur gick första timmen?
3. **18:35 CET (12:35 EST):** 2h-utvärdering — andra timmen?
4. **23:00 CET (17:00 EST):** EOD-utvärdering — dagslut
5. **Discord:** Automatisk rapport med resultat och historisk accuracy

### Manuell utvärdering

```bash
# Utvärdera en specifik trigger
python -c "from src.trigger_system_v1 import evaluate_trigger; print(evaluate_trigger('NVDA'))"

# Visa dagens triggers
python -c "from src.trigger_system_v1 import get_todays_triggers; print(get_todays_triggers())"

# Historisk accuracy
python -c "from src.trigger_system_v1 import get_historical_accuracy; print(get_historical_accuracy('NVDA'))"
```

### Backtesting

Testa strategier mot historisk data:

```bash
# Senaste 30 dagar, alla aktier
python src/backtest.py --days 30 --all

# Specifik period
python src/backtest.py --start 2026-01-01 --end 2026-03-31 --symbols NVDA,WMT

# Output sparas i:
# - data/triggers.db (tabell backtest_results)
# - reports/backtest_report_YYYY-MM-DD.md
```

### Sektorkorrelation (Nivå 2)

Förstå om triggers faktiskt förutsäger marknadsriktning:

```bash
# Backtest med sektorkorrelation
python src/backtest.py --days 30 --symbols NVDA,TGT,LOW
# Output inkluderar nu sektor-accuracy:
# "3/5 triggers slog igenom, 2/3 sektorer rörde sig i förväntad riktning"
```

**Korrelationslogik:**
- Trigger HIT + bullish + sektor UPP = ✅ Korrekt
- Trigger HIT + bearish + sektor NER = ✅ Korrekt
- Trigger MISS + bullish + sektor NER = ✅ Korrekt (motsatt riktning)
- Trigger HIT + bullish + sektor NER = ❌ Fel

### MCP-server (AI-integration)

Integrera med Claude, Cursor eller annan AI-assistent:

```json
{
  "mcpServers": {
    "trading-triggers": {
      "command": "python",
      "args": ["/Users/xandgo/dev/trading-triggers/src/mcp_server.py"]
    }
  }
}
```

**Tillgängliga tools:**
- `get_todays_triggers` — Lista dagens aktiva triggers
- `evaluate_trigger` — Utvärdera specifik trigger manuellt
- `get_historical_accuracy` — Träffsäkerhet över tid
- `get_market_summary` — Marknadsöversikt för alla aktier
- `add_stock` — Lägg till ny aktie i bevakning
- `remove_stock` — Ta bort aktie från bevakning
- `get_trigger_stats` — Detaljerad statistik per trigger-typ
- `export_to_obsidian` — Exportera rapport till Obsidian

---

## Projektstruktur

```
valvet-trading-triggers/
├── src/
│   ├── trigger_system_v1.py      # Huvudmotor — triggers, eval, Discord
│   ├── backtest.py                # Backtesting mot historisk data
│   ├── sector_analysis.py         # Sektorkorrelation (bullish/bearish)
│   ├── resilience.py              # Retry + Circuit Breaker
│   ├── mcp_server.py              # MCP-server med 8 tools
│   └── poc_trigger_system.py      # Proof of Concept
├── tests/
│   ├── test_resilience.py         # 8 enhetstester
│   ├── test_trigger_system_retry.py  # 3 integrationstester
│   ├── test_backtest.py           # 9 backtest-tester
│   └── test_sector_analysis.py    # 23 sektor-tester
├── config/
│   └── .env.example               # Miljövariabel-template
├── data/
│   └── triggers.db                # SQLite-databas
├── reports/                       # Genererade rapporter
├── docs/                          # Design-dokument
├── requirements.txt               # Python-dependencies
├── run_daily.sh                   # Huvudskript (eval + webhook)
├── run_with_webhook.sh            # Med Discord-notifiering
├── PLAN.md                        # Utvecklingsplan
└── README.md                      # Denna fil
```

---

## Teknisk dokumentation

### Databasschema (SQLite)

```sql
-- Triggers (huvudtabell)
CREATE TABLE triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    condition TEXT NOT NULL,
    target_price REAL,
    trigger_time TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Utvärderingar (resultat)
CREATE TABLE evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_id INTEGER NOT NULL,
    result TEXT NOT NULL,  -- "hit", "miss", "error"
    current_price REAL,
    target_price REAL,
    evaluation_time TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trigger_id, evaluation_time)  -- Idempotens
);

-- Backtest-resultat
CREATE TABLE backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    open_price REAL,
    close_price REAL,
    result TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, evaluation_time)
);

-- Sektorkorrelation (Nivå 2)
CREATE TABLE backtest_sector_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_result_id INTEGER,
    symbol TEXT NOT NULL,
    target_date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    direction TEXT NOT NULL,  -- "bullish", "bearish", "neutral"
    sector_etf TEXT NOT NULL,
    sector_change_percent REAL,
    sector_correlated INTEGER NOT NULL,  -- 0 eller 1
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(backtest_result_id, symbol, target_date, evaluation_time)
);
```

### Resilience & Retry

**Retry-logik (Yahoo Finance):**
- 3 försök med exponentiell backoff (4–10 sekunder)
- Hanterar tillfälliga nätverksfel

**Circuit Breaker (Discord):**
- Öppnas efter 3 misslyckade webhook-anrop i rad
- Blockerar i 5 minuter
- Återställs efter 15 minuters inaktivitet
- Tillåter ett test-anrop i "half-open" tillstånd

```python
from src.resilience import retry_yfinance, discord_circuit_breaker

@retry_yfinance
def fetch_stock_data(symbol: str) -> dict:
    """Automatiska retries vid tillfälliga fel."""
    ...

if discord_circuit_breaker.can_execute():
    send_discord_notification()
    discord_circuit_breaker.record_success()
else:
    logger.warning("Discord webhook tillfälligt blockerad")
```

### Trigger-evaluering

**Logik:**
1. Hämta aktuellt pris från Yahoo Finance
2. Jämför med trigger-villkor (t.ex. "stigande minst 1% från open")
3. Spara resultat i evaluations-tabellen
4. Skicka Discord-rapport med historisk accuracy

**Evaluation times:**
- `1h`: Efter första timmen (10:35 EST / 16:35 CET)
- `2h`: Efter andra timmen (12:35 EST / 18:35 CET)
- `EOD`: End of day (17:00 EST / 23:00 CET)

### Sektorkorrelation (Nivå 2)

**Riktningsextraktion:**
- Regelbaserad nyckelords-matchning från trigger-text
- Bullish: "momentum", "accelerera", "stiga", "över", "konstruktiv"
- Bearish: "nedställ", "svaghet", "under", "falla", "risk"
- Kontextberoende: "bryter över resistance" → bullish, "stannar vid resistance" → bearish

**Sektorkarta (exempel):**
| Aktie | Sektordf | ETF |
|-------|---------|-----|
| NVDA, AMD, ARM | Semiconductors | SOXX |
| TGT, WMT, COST | Consumer Discretionary | XLY |
| LOW, HD | Home Improvement | ITB |

---

## Utvecklingsstatus

### Nivå 1 — Trigger-hits ✅
- [x] Retry-logik för Yahoo Finance (`tenacity`)
- [x] Circuit Breaker för Discord-webhook
- [x] Backtesting-motor
- [x] 20 tester (resilience + backtest)

### Nivå 2 — Sektorkorrelation ✅
- [x] Riktningsextraktion (bullish/bearish)
- [x] Sektor-ETF-mappning (60+ aktier)
- [x] Korrelationslogik (trigger + sektor-rörelse)
- [x] 23 tester (sector_analysis)

### Nivå 3 — Köp/sälj-signaler 🔄
- [ ] Confidence score-algoritm
- [ ] Signalstyrka (1-5)
- [ ] Discord-signaler
- [ ] Hypotetisk P&L-backtesting

### Kommande
- [ ] Obsidian-export med automatisk commit/push
- [ ] Docker-container
- [ ] Reservkällor (Alpha Vantage, IEX, Polygon)

---

## Testning

```bash
# Kör alla tester (utom MCP-server som kräver extra dependencies)
python3 -m pytest tests/test_resilience.py tests/test_trigger_system_retry.py tests/test_backtest.py tests/test_sector_analysis.py -v

# Resultat: 43/43 tester passerar
```

---

## Teknisk stack

- **Python 3.13** — Huvudspråk
- **SQLite** — Databas (enkel, filbaserad)
- **yfinance** — Primär datakälla (Yahoo Finance)
- **tenacity** — Retry-logik
- **aiohttp** — Discord-webhook
- **mcp** — MCP-server SDK (för AI-integration)
- **pandas** — Datahantering

---

## Vanliga frågor

**Q: Behöver jag OpenClaw för att använda systemet?**
A: Nej! Systemet är helt fristående. OpenClaw/MCP-integration är valfri.

**Q: Kan jag använda det utan Discord?**
A: Ja. Kör `python src/trigger_system_v1.py` istället för `run_with_webhook.sh`.

**Q: Var sparas data?**
A: Allt sparas lokalt i `data/triggers.db` (SQLite). Ingen molnlagring krävs.

**Q: Hur lägger jag till nya aktier?**
A: Via MCP-servern (`add_stock`-tool) eller manuellt i databasen.

**Q: Kan jag köra på Windows/Linux?**
A: Ja, men LaunchAgent-schemaläggning är macOS-specifik. Använd cron eller Task Scheduler istället.

---

## Dokument

- [`PLAN.md`](PLAN.md) — Utvecklingsplan med nivåer och roadmap
- [`docs/requirements.md`](docs/requirements.md) — Kravspecifikation
- [`docs/tech-spec.md`](docs/tech-spec.md) — Teknisk specifikation
- [`docs/design.md`](docs/design.md) — Systemdesign

---

## Licens

MIT — Använd fritt, bidra gärna!

---

*Byggt med 💚 för att slippa manuellt kolla aktiekurser kl 16:30 varje dag.*
