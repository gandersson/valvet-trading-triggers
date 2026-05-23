# Trading Triggers — Utvecklingsplan

**Status:** Nivå 2 klar (2026-05-23) | **Nästa milstolpe:** Nivå 3 — Köp/sälj-signaler

---

## 🎯 Nivåer (Ny arkitektur)

Systemet utvärderas i tre nivåer, där varje nivå bygger på föregående:

| Nivå | Vad som mäts | Status |
|------|-------------|--------|
| **Nivå 1** | Slog trigger igenom? (prisnivå) | ✅ Klar |
| **Nivå 2** | Korrelerade trigger med sektorn? (bullish/bearish) | ✅ Klar |
| **Nivå 3** | Köp/sälj-råd baserat på N1+N2 + historisk accuracy | 🔄 Kommande |

**Nyckelinsikt:** Det är inte "rätt" eller "fel" att en trigger slår — det viktiga är om **marknaden reagerade i den förväntade riktningen** när den gjorde det.

---

## ✅ Färdigt (MVP — Vecka 1–2)

- [x] Data Collector (yfinance)
- [x] SQLite-databas med 4 tabeller (inkl. UNIQUE constraint)
- [x] 5 grundläggande triggers (NVDA, WMT, TTWO, WDAY, ENPH)
- [x] Discord-webhook med embeds (inkl. evaluation_time i titel)
- [x] 1h-utvärdering (kl 16:35 CET)
- [x] 2h-utvärdering (kl 18:35 CET)
- [x] EOD-utvärdering (kl 23:00 CET)
- [x] Idempotens — INSERT OR REPLACE via UNIQUE(trigger_id, evaluation_time)
- [x] Historisk statistik (träffsäkerhet per trigger)
- [x] Automatisk körning via LaunchAgent (vardagar, 3 tider)
- [x] Dokumentation i Obsidian + GitHub
- [x] **CI/GitHub Actions** — ruff linting aktiv, bygget går igenom
- [x] **MCP-server** — 8 tools implementerade

---

## ✅ Nivå 1 — Trigger-hits (Vecka 3, 2026-05-23)

**Mål:** Mäta om trigger-villkoret uppfylls (prisnivå)

**Status:** ✅ Klar

**Implementation:**
- ✅ Retry-logik för Yahoo Finance (`tenacity`, 3 försök, exp backoff)
- ✅ Circuit Breaker för Discord-webhook (3 fel → 5 min block)
- ✅ `src/resilience.py` — retry_yfinance decorator + CircuitBreaker klass
- ✅ `fetch_stock_data()` låter exceptions bubbla upp för retry
- ✅ `send_discord_report()` skyddad av circuit breaker
- ✅ 11 tester (8 enhetstester + 3 integrationstester)

---

## ✅ Nivå 2 — Sektorkorrelation (Vecka 4, 2026-05-23)

**Mål:** Mäta om trigger riktning stämmer överens med sektormomentum

**Status:** ✅ Klar

**Implementation:**
- ✅ `src/sector_analysis.py` — ny modul
  - `extract_direction()` — parsar bullish/bearish från trigger-text (regelbaserad nyckelords-matchning)
  - `get_sector_etf()` — mappar aktier → sektor-ETF (60+ aktier)
  - `fetch_sector_data()` — hämtar sektordata via yfinance med retry
  - `evaluate_sector_correlation()` — korrelationslogik (trigger + riktning + sektor-rörelse)
  - `analyze_backtest_sector_correlation()` — sammanfattning per sektor
- ✅ Uppdaterad `src/backtest.py` — berikar resultat med direction, sector_etf, sector_correlated
- ✅ Ny tabell `backtest_sector_analysis` i SQLite
- ✅ Markdown-export med sektorkorrelationsstatistik
- ✅ 23 tester i `tests/test_sector_analysis.py`

**Korrelationslogik:**
| Trigger | Sektor | Resultat |
|---------|--------|----------|
| HIT + bullish + sektor UPP | ✅ Korrekt |
| HIT + bullish + sektor NER | ❌ Fel |
| HIT + bearish + sektor NER | ✅ Korrekt |
| HIT + bearish + sektor UPP | ❌ Fel |
| MISS + bullish + sektor NER | ✅ Korrekt (motsatt riktning) |
| MISS + bearish + sektor UPP | ✅ Korrekt (motsatt riktning) |

---

## 🔄 Nivå 3 — Köp/sälj-signaler (Vecka 5, 2026-06)

**Mål:** Generera köp/sälj-råd baserat på Nivå 1 + Nivå 2 + historisk accuracy

**Koncept:**
- När en trigger inträffar → kontrollera historisk accuracy för den aktien
- Om Nivå 2-korrelationen är hög (>70%) → ge köp/sälj-signal
- Signalstyrka baserad på:
  - Trigger-historik (hur ofta den slår)
  - Sektor-korrelation (hur ofta riktningen stämmer)
  - Kombinerad confidence score

**Implementation (planerat):**
- [ ] `src/signal_generator.py` — signalgenerering
- [ ] Confidence score-algoritm (N1 * N2 * historisk accuracy)
- [ ] Discord-signal med styrka (1-5)
- [ ] Backtesting av signaler (hypotetisk P&L)

---

## 🚧 Kommande (Vecka 5–6)

### Backtesting (Nivå 1+2)
**Status:** ✅ Klar (2026-05-23)

**Kommando:**
```bash
python src/backtest.py --days 90 --symbols NVDA,WMT,TTWO
python src/backtest.py --days 30 --all
```

---

### Obsidian-export
**Mål:** Spara dagliga rapporter direkt i Obsidian-vaulten

**Implementation:**
- Skapa markdown-fil i `Valvet/Trading Triggers/YYYY-MM-DD.md`
- Inkludera:
  - Trigger-resultat med tabeller
  - Sektor-korrelationsstatistik
  - Historisk accuracy
  - Köp/sälj-signaler (Nivå 3)
- Committa och pusha automatiskt

**Filformat:**
```markdown
# Trading Trigger Rapport — 2026-05-23

## Resultat
| Aktie | Trigger | Nivå 1 | Nivå 2 | Sektor |
|-------|---------|--------|--------|--------|
| NVDA | Återtar $225 | ✅ HIT | ✅ Korrekt (SOXX +2.1%) | SOXX |

## Sammanfattning
- 3/5 triggers slog igenom (60%)
- 2/3 sektorer rörde sig i förväntad riktning (67%)
- Köp-signaler: 2 (NVDA, ARM)
```

---

### Docker-container
**Mål:** Kör systemet i isolerad container

**Fördelar:**
- Oavhängig av lokala Python-versioner
- Enklare att flytta mellan maskiner
- Bättre reproducerbarhet

**Dockerfile:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
CMD ["python", "src/trigger_system_v1.py"]
```

---

### CI/CD (GitHub Actions)
**Status:** ⏸️ Pausad tills vidare (2026-05-23)

**Bakgrund:**
- Workflow-filen `.github/workflows/ci.yml` togs bort eftersom pipelinen endast körde ruff linting utan att bidra med mervärde
- MyPy och pytest var utkommenterade pga saknade dependencies (mcp-modulen)

**När den återaktiveras:**
När följande kriterier är uppfyllda:
1. `mcp`-modulen finns tillgänglig på PyPI (eller vi ersätter den)
2. Vi har en tydlig teststrategi som ger värde (t.ex. pre-commit hooks, nightly runs)
3. Vi har tid att underhålla pipelinen

**Framtida önskemål:**
- Pre-commit hooks för ruff (lokalt, innan push)
- Nightly testkörning mot riktig data
- Automatisk Obsidian-export vid framgångsrik körning
- Release-tagging vid milstolpar

**Åtgärd:** Lägg till `mcp` i requirements.txt och återaktivera workflow när lämpligt.

---

### Reservkällor
**Mål:** Hantera om Yahoo Finance är nere

**Alternativa källor:**
- Alpha Vantage (API-nyckel krävs)
- IEX Cloud (API-nyckel krävs)
- Polygon.io (API-nyckel krävs)

**Implementation:**
```python
def fetch_with_fallback(symbol):
    try:
        return fetch_yahoo(symbol)
    except:
        try:
            return fetch_alphavantage(symbol)
        except:
            return fetch_iex(symbol)
```

---

## 📅 Prioriterad roadmap

### Vecka 3 (2026-05-23) ✅
1. [x] **MCP-server** — 8 tools implementerade och testade
2. [x] **2h-utvärdering** (18:35 CET) — idempotent, LaunchAgent-schemalagd
3. [x] **EOD-utvärdering** (23:00 CET) — idempotent, LaunchAgent-schemalagd
4. [x] **Nivå 1** — Retry + Circuit Breaker + backtesting

### Vecka 4 (2026-05-23) ✅
1. [x] **Nivå 2** — Sektorkorrelation med bullish/bearish-riktning
2. [x] Förbättrad backtesting med sektordata
3. [x] 43 tester passerar (20 + 23)

### Vecka 5 (2026-06-09) 🔄
1. [ ] **Nivå 3** — Köp/sälj-signaler med confidence score
2. [ ] Obsidian-export med automatisk commit/push
3. [ ] Docker-container

### Vecka 6 (2026-06-16)
1. [ ] Reservkällor (Alpha Vantage, IEX)
2. [ ] Dokumentation och tester för Nivå 3
3. [ ] Produktionsövervakning

---

## 🔧 Teknisk skuld

- Återaktivera mypy i CI när `mcp` type stubs finns
- Återaktivera pytest i CI när `mcp` finns i requirements.txt
- Fixa type annotations i `poc_trigger_system.py`
- Stemming för svenska böjningsformer i direction-extraktion
- Viktade nyckelord för bättre precision

---

## 📊 Testtäckning

| Modul | Tester | Status |
|-------|--------|--------|
| `test_resilience.py` | 8 | ✅ Passerar |
| `test_trigger_system_retry.py` | 3 | ✅ Passerar |
| `test_backtest.py` | 9 | ✅ Passerar |
| `test_sector_analysis.py` | 23 | ✅ Passerar |
| **Totalt** | **43** | **✅ Alla passerar** |

---

*Senast uppdaterad: 2026-05-23*
*Av: Marvin 🤖*
