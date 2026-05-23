# Trading Trigger System — Projektplan

**Skapad:** 2026-05-22  
**Status:** Planering klar — redo för implementation  
**Mål:** Automatiserat system för trigger-tracking med MCP-server

---

## 📋 Leverabler från subagenter

| Agent | Fil | Storlek | Status |
|-------|-----|---------|--------|
| Kravställare (marknad) | `requirements.md` | ~15 KB | ✅ Klar |
| Teknisk kravställare | `tech-spec.md` | ~17 KB | ✅ Klar |
| Systemdesigner | `design.md` | ~40 KB | ✅ Klar |

---

## 🏗️ Arkitektur (5 huvudkomponenter)

1. **Market Data Collector** — Hämtar kurser från Yahoo Finance → Alpha Vantage → Polygon (fallback-kedja)
2. **Trigger Manager** — Skapar, aktiverar och hanterar triggers med tillståndsmaskin
3. **Evaluation Engine** — Utvärderar triggers vid 1h, 2h, EOD
4. **MCP Server** — Exponerar tools: `evaluate_trigger`, `get_stock_quote`, `run_daily_analysis`, etc.
5. **Notifier** — Discord-rapporter, eventuellt email

---

## 🛠️ Teknisk Stack

| Komponent | Teknik |
|-----------|--------|
| Språk | Python 3.12+ |
| API | FastAPI (ASGI) |
| DB | SQLite (dev) → PostgreSQL (prod) |
| Cache/Queue | Redis + Celery + Celery Beat |
| Data | yfinance (primär), Alpha Vantage/Polygon (fallback) |
| Deploy | Docker Compose på Mac mini → eventuellt Fly.io/Railway |
| CI/CD | GitHub Actions |
| Testing | pytest + pytest-asyncio (mål: 80%+ coverage) |

---

## 📅 Utvecklingsplan (8 veckor)

### Fas 1: MVP — Vecka 1–2
- [ ] Market Data Collector (Yahoo Finance + fallback)
- [ ] SQLite-databas + modeller (SQLAlchemy)
- [ ] Grundläggande triggers (5 typer: pris, volym, rörelse, marknad, makro)
- [ ] Evaluation Engine — utvärdering efter 1h
- [ ] Discord-notifiering med enkel sammanfattning
- [ ] Cron-jobb med APScheduler

### Fas 2: MCP + Historik — Vecka 3–4
- [ ] MCP-server med 5 tools
- [ ] Utvärdering efter 2h och EOD
- [ ] Historisk statistik-beräkning (hit-rate per trigger-typ)
- [ ] Retry-logik och felhantering (circuit breaker)
- [ ] Konfiguration via YAML/JSON

### Fas 3: Avancerat — Vecka 5–6
- [ ] Reservdatakällor fullt integrerade
- [ ] Backtest-engine (köra historiska triggers retroaktivt)
- [ ] Förbättrade notifieringar (formatting, @mentions vid träffar)
- [ ] Obsidian-export av rapporter
- [ ] Docker-containerisering

### Fas 4: Produktion — Vecka 7–8
- [ ] PostgreSQL-migration
- [ ] GitHub Actions CI/CD (test, lint, typecheck)
- [ ] Fullständig dokumentation
- [ ] (Valfritt) Cloud-deploy till Fly.io/Railway
- [ ] Grafana/dashboard för monitoring (valfritt)

---

## 📁 GitHub-repo-struktur

```
valvet-trading-triggers/           # GitHub-repo
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Test + lint på push
│       └── deploy.yml           # (senare) Deploy till cloud
├── src/
│   ├── api/                      # FastAPI + MCP-server
│   ├── collectors/               # Data-hämtning
│   ├── triggers/                 # Trigger-logik + tillståndsmaskin
│   ├── storage/                  # DB-modeller + repositories
│   ├── notifications/            # Discord, email
│   ├── scheduler/                # Celery-jobb
│   ├── reports/                  # Rapportgenerering
│   ├── mcp/                      # MCP-tools
│   └── utils/                    # Hjälpfunktioner
├── config/
│   ├── stocks.yaml               # Aktier vi trackar
│   └── triggers/
│       └── default_rules.yaml    # Trigger-regler
├── tests/
│   ├── unit/                     # Enhetstester
│   └── integration/              # Integrationstester
├── scripts/
│   ├── init_db.py
│   └── health_check.py
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
├── README.md
└── DESIGN.md                     # (denna fil + tech-spec)
```

---

## 🔌 MCP-Server Tools (slutlig spec)

| Tool | Beskrivning |
|------|-------------|
| `get_todays_triggers` | Lista dagens aktiva triggers och status |
| `get_trigger_result` | Resultat för specifik aktie/trigger |
| `get_historical_accuracy` | Träffsäkerhet över tid |
| `get_market_summary` | Dagens marknadsöversikt |
| `add_trigger` | Lägg till ny trigger manuellt |
| `evaluate_trigger` | Tvinga utvärdering nu |
| `get_stock_quote` | Nuvarande kurs för aktie |
| `run_daily_analysis` | Generera dagens rapport |

---

## 🚀 Nästa steg — Vad vill du göra?

1. **Sätta upp GitHub-repo** nu och börja koda MVP (Fas 1)
2. **Reviewa dokumenten** först — kommentera ändringar
3. **Starta med en PoC** — enklare variant först (t.ex. bara Yahoo Finance + SQLite + Discord)
4. **Dela upp arbetet** — jag spawnar kodnings-subagenter per komponent

**Rekommendation:** Börja med PoC (Proof of Concept) — en Python-fil som:
- Hämtar 5 aktier från Yahoo Finance
- Utvärderar enkla triggers
- Skickar Discord-meddelande
- Sparar till SQLite

Det ger snabb feedback och vi kan iterera.

---

## 📝 Anteckningar

- API-nycklar behövs: Alpha Vantage (gratis), Polygon (valfritt)
- Discord webhook-URL behöver konfigureras
- Systemet ska köra på din Mac mini (Rocket) lokalt initialt
- SQLite räcker tills vi har >10 000 utvärderingar/dag

*Senast uppdaterad: 2026-05-22*
