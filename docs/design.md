# Trading Trigger System — Design Document

**Version:** 1.0  
**Datum:** 2026-05-22  
**Författare:** System Designer (subagent)  
**Mål:** Automatiserat system för att spåra, utvärdera och rapportera trading-triggers för aktier

---

## 1. Övergripande Arkitektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRADING TRIGGER SYSTEM                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │   Discord   │     │   CLI/      │     │   Cron      │               │
│  │   Bot       │◄────┤   API       │◄────┤   Scheduler │               │
│  └─────────────┘     │   (MCP)     │     └─────────────┘               │
│                      └──────┬──────┘                                  │
│                             │                                         │
│                      ┌──────▼──────┐                                  │
│                      │  MCP Server │                                   │
│                      │  (FastAPI)  │                                   │
│                      └──────┬──────┘                                  │
│                             │                                         │
│        ┌────────────────────┼────────────────────┐                   │
│        │                    │                    │                   │
│  ┌─────▼─────┐      ┌───────▼───────┐   ┌──────▼──────┐            │
│  │  Trigger  │      │    Market     │   │  Evaluation │            │
│  │  Manager  │◄────►│    Data       │   │   Engine    │            │
│  │           │      │   Collector   │   │             │            │
│  └─────┬─────┘      └───────────────┘   └──────┬──────┘            │
│        │                                         │                   │
│        │              ┌────────────────────────┘                   │
│        │              │                                              │
│  ┌─────▼──────────────▼──────┐                                     │
│  │      Storage Layer        │                                     │
│  │  (SQLite → PostgreSQL)  │                                     │
│  └───────────────────────────┘                                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Dataflöde
1. **Cron Scheduler** triggar varje morgon kl 06:30 ET (12:30 svensk tid) för förbörsrapport
2. **Market Data Collector** hämtar aktuella kurser, nyheter och makrodata från externa API:er
3. **Trigger Manager** skapar dagens triggers baserat på regler och marknadsläge
4. **Evaluation Engine** utvärderar triggers efter 1h, 2h, end-of-day
5. **MCP Server** exponerar all data via ett enhetligt API
6. **Notifier** skickar rapporter till Discord och/eller email

---

## 2. Komponentbeskrivningar

### 2.1 Market Data Collector
**Ansvar:** Hämta realtids- och historisk marknadsdata

**Källor:**
| Källa | Data | Kostnad | Begränsning |
|-------|------|---------|-------------|
| Yahoo Finance (unofficial) | Kurser, volym | Gratis | Ingen garanti, rate limits |
| Alpha Vantage | Kurser, teknisk analys | Freemium | 25 calls/dag gratis |
| Finnhub | Realtime WebSocket | Freemium | 60 calls/minut |
| NewsAPI | Nyheter, sentiment | Freemium | 1000 requests/dag |
| FRED (Federal Reserve) | Makrodata | Gratis | USA-fokuserad |

**Gränssnitt:**
```python
class MarketDataCollector:
    async def get_current_price(symbol: str) -> PriceQuote
    async def get_historical_prices(symbol: str, period: str) -> List[PriceBar]
    async def get_news(symbol: str, limit: int) -> List[NewsItem]
    async def get_macro_data(indicator: str) -> MacroDataPoint
```

### 2.2 Trigger Manager
**Ansvar:** Skapa, aktivera och hantera triggers baserat på regler

**Trigger-typer:**
- **Price Trigger:** Aktie når/prickar ett prisnivå
- **Range Trigger:** Aktie håller sig inom/utanför ett intervall
- **Momentum Trigger:** Procentuell förändring över tröskel
- **Macro Trigger:** Makrohändelse (ränta, olja, CPI)
- **News Trigger:** Sentiment-baserad från nyheter

**Gränssnitt:**
```python
class TriggerManager:
    async def create_trigger(symbol: str, type: TriggerType, 
                            conditions: Dict, expiry: datetime) -> Trigger
    async def activate_trigger(trigger_id: UUID) -> None
    async def evaluate_trigger(trigger_id: UUID, 
                                market_data: MarketSnapshot) -> EvaluationResult
    async def archive_trigger(trigger_id: UUID, result: EvaluationResult) -> None
```

### 2.3 Evaluation Engine
**Ansvar:** Utvärdera triggers mot verklig marknadsdata

**Utvärderingsfrekvens:**
| Typ | Frekvens | Exempel |
|-----|----------|---------|
| Pre-market | 06:30 ET | Förbörsrapport |
| First Hour | 10:30 ET | Efter öppning |
| Mid-day | 13:00 ET | Lunchupdate |
| End of Day | 16:00 ET | Daglig sammanfattning |

**Gränssnitt:**
```python
class EvaluationEngine:
    async def evaluate_all_active(timeframe: TimeFrame) -> List[EvaluationResult]
    async def evaluate_single(trigger: Trigger, 
                               data: MarketSnapshot) -> EvaluationResult
    def calculate_accuracy(historical_results: List[EvaluationResult]) -> Metrics
```

### 2.4 MCP Server (FastAPI)
**Ansvar:** Exponera all funktionalitet via ett RESTful API

**Endpoints:**
```
GET  /api/v1/triggers              # Lista aktiva triggers
POST /api/v1/triggers              # Skapa ny trigger
GET  /api/v1/triggers/{id}         # Hämta specifik trigger
GET  /api/v1/triggers/{id}/evaluate # Utvärdera trigger nu
GET  /api/v1/market/summary        # Dagens marknadssammanfattning
GET  /api/v1/market/quote/{symbol} # Aktuell kurs
GET  /api/v1/reports/daily         # Dagens rapport
GET  /api/v1/reports/history     # Historisk trigger-data
GET  /api/v1/metrics/accuracy    # Trigger-träffsäkerhet
```

### 2.5 Notifier
**Ansvar:** Skicka rapporter och alertar till externa kanaler

**Kanaler:**
- **Discord:** Webhook-baserade meddelanden med embeds
- **Email:** HTML-baserade rapporter via SMTP
- **Slack:** Webhook API
- **Console:** Lokala loggar och stdout

**Gränssnitt:**
```python
class Notifier:
    async def send_trigger_alert(trigger: Trigger, result: EvaluationResult)
    async def send_daily_report(report: DailyReport)
    async def send_error_alert(error: SystemError)
```

---

## 3. Databasschema

### 3.1 Entiteter och Relationer

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   stocks    │◄─────►│  triggers   │◄─────►│ evaluations │
└─────────────┘       └─────────────┘       └─────────────┘
       │                     │                      │
       │              ┌──────▼──────┐              │
       │              │  trigger_   │              │
       └─────────────►│  history    │◄─────────────┘
                      └─────────────┘
```

### 3.2 Tabelldefinitioner (SQLite/PostgreSQL)

```sql
-- Aktier vi trackar
CREATE TABLE stocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL UNIQUE,        -- NVDA, WMT, etc.
    name            TEXT NOT NULL,               -- NVIDIA Corporation
    sector          TEXT,                        -- Technology
    market_cap      BIGINT,                     -- i USD
    beta            REAL,                       -- Risk-mått
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Triggers (regler/observationer)
CREATE TABLE triggers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id        INTEGER NOT NULL REFERENCES stocks(id),
    trigger_type    TEXT NOT NULL,              -- PRICE, RANGE, MOMENTUM, MACRO, NEWS
    description     TEXT NOT NULL,              -- "Håller sig stark i första timmen"
    conditions      JSON NOT NULL,              -- {"threshold": 220.0, "direction": "above"}
    
    -- Tillståndsmaskin
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft, active, evaluating, hit, miss, expired, archived
    
    -- Tidsstämplar
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at    TIMESTAMP,                  -- När den blir aktiv
    expires_at      TIMESTAMP,                  -- När den slutar gälla
    evaluated_at    TIMESTAMP,                -- När utvärderingen gjordes
    
    -- Metadata
    source          TEXT,                     -- manual, auto_generated, mcp_request
    created_by      TEXT,                     -- user_id eller system
    tags            JSON                      -- ["tech", "earnings", "macro"]
);

-- Utvärderingar (resultat)
CREATE TABLE evaluations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_id      INTEGER NOT NULL REFERENCES triggers(id),
    
    -- Utvärderingsdata
    evaluated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    timeframe       TEXT NOT NULL,             -- first_hour, mid_day, eod
    
    -- Marknadsdata vid utvärdering
    open_price      REAL,
    high_price      REAL,
    low_price       REAL,
    current_price   REAL,
    volume          BIGINT,
    market_context  JSON,                     -- {"sp500_change": 0.5, "vix": 17.2}
    
    -- Resultat
    result          TEXT NOT NULL,             -- hit, miss, pending, error
    result_details  TEXT,                     -- Beskrivning av varför
    confidence      REAL,                     -- 0.0 - 1.0
    
    -- Metadata
    data_source     TEXT,                     -- yahoo, alpha_vantage, etc.
    latency_ms      INTEGER                   -- API-latens
);

-- Trigger-historik (tillståndsövergångar)
CREATE TABLE trigger_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_id      INTEGER NOT NULL REFERENCES triggers(id),
    from_status     TEXT NOT NULL,
    to_status       TEXT NOT NULL,
    changed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason          TEXT,
    metadata        JSON
);

-- Dagliga rapporter
CREATE TABLE daily_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date     DATE NOT NULL UNIQUE,
    total_triggers  INTEGER DEFAULT 0,
    hits            INTEGER DEFAULT 0,
    misses          INTEGER DEFAULT 0,
    accuracy_rate   REAL,
    report_data     JSON NOT NULL,           -- Full rapportstruktur
    sent_to         JSON,                    -- ["discord", "email"]
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- System-konfiguration
CREATE TABLE config (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index för snabb sökning
CREATE INDEX idx_triggers_status ON triggers(status);
CREATE INDEX idx_triggers_expires ON triggers(expires_at);
CREATE INDEX idx_evaluations_trigger ON evaluations(trigger_id);
CREATE INDEX idx_evaluations_time ON evaluations(evaluated_at);
CREATE INDEX idx_history_trigger ON trigger_history(trigger_id);
```

---

## 4. API-Design

### 4.1 Externa API:er (Inkommande data)

| API | Endpoint | Användning | Rate Limit |
|-----|----------|-----------|------------|
| Yahoo Finance | `finance.yahoo.com/quote/{sym}` | Kurser, nyheter | ~200/hr IP-baserat |
| Alpha Vantage | `alphavantage.co/query` | Historisk data | 25/dag gratis |
| Finnhub | `finnhub.io/api/v1` | Realtids-WebSocket | 60/minut |
| NewsAPI | `newsapi.org/v2` | Nyheter | 1000/dag |

### 4.2 Internt MCP-API (Utgående data)

**Bas-URL:** `http://localhost:8000/api/v1`

```yaml
openapi: 3.0.0
info:
  title: Trading Trigger MCP API
  version: 1.0.0

paths:
  /triggers:
    get:
      summary: Lista triggers med filter
      parameters:
        - name: status
          in: query
          schema: { type: string, enum: [active, hit, miss, archived] }
        - name: symbol
          in: query
          schema: { type: string }
        - name: date
          in: query
          schema: { type: string, format: date }
      responses:
        200:
          description: Lista med triggers
          content:
            application/json:
              schema:
                type: object
                properties:
                  triggers:
                    type: array
                    items: { $ref: '#/components/schemas/Trigger' }
                  total: { type: integer }
                  page: { type: integer }

    post:
      summary: Skapa ny trigger
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [symbol, trigger_type, conditions, description]
              properties:
                symbol: { type: string, example: "NVDA" }
                trigger_type: { type: string, enum: [PRICE, RANGE, MOMENTUM, MACRO, NEWS] }
                conditions: { type: object }
                description: { type: string }
                expires_at: { type: string, format: date-time }
      responses:
        201:
          description: Trigger skapad
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Trigger' }

  /triggers/{id}/evaluate:
    post:
      summary: Tvinga utvärdering av trigger
      parameters:
        - name: id
          in: path
          required: true
          schema: { type: integer }
      responses:
        200:
          description: Utvärderingsresultat
          content:
            application/json:
              schema: { $ref: '#/components/schemas/EvaluationResult' }

  /market/summary:
    get:
      summary: Dagens marknadssammanfattning
      responses:
        200:
          description: Marknadsöversikt
          content:
            application/json:
              schema:
                type: object
                properties:
                  indices:
                    type: object
                    properties:
                      sp500: { $ref: '#/components/schemas/IndexData' }
                      nasdaq: { $ref: '#/components/schemas/IndexData' }
                      dow: { $ref: '#/components/schemas/IndexData' }
                  top_movers:
                    type: array
                    items: { $ref: '#/components/schemas/StockMover' }
                  macro:
                    type: object
                    properties:
                      ten_year_yield: { type: number }
                      vix: { type: number }
                      oil_price: { type: number }

  /reports/daily:
    get:
      summary: Hämta dagens rapport
      parameters:
        - name: date
          in: query
          schema: { type: string, format: date }
      responses:
        200:
          description: Daglig trigger-rapport
          content:
            application/json:
              schema: { $ref: '#/components/schemas/DailyReport' }

  /metrics/accuracy:
    get:
      summary: Trigger-träffsäkerhet över tid
      parameters:
        - name: period
          in: query
          schema: { type: string, enum: [7d, 30d, 90d, 1y], default: 30d }
        - name: symbol
          in: query
          schema: { type: string }
      responses:
        200:
          description: Träffsäkerhets-metriska
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_triggers: { type: integer }
                  hits: { type: integer }
                  misses: { type: integer }
                  accuracy_rate: { type: number }
                  by_symbol:
                    type: object
                    additionalProperties:
                      type: object
                      properties:
                        total: { type: integer }
                        hits: { type: integer }
                        accuracy: { type: number }

components:
  schemas:
    Trigger:
      type: object
      properties:
        id: { type: integer }
        symbol: { type: string }
        trigger_type: { type: string }
        description: { type: string }
        conditions: { type: object }
        status: { type: string }
        created_at: { type: string, format: date-time }
        activated_at: { type: string, format: date-time }
        expires_at: { type: string, format: date-time }
        tags: { type: array, items: { type: string } }

    EvaluationResult:
      type: object
      properties:
        trigger_id: { type: integer }
        evaluated_at: { type: string, format: date-time }
        timeframe: { type: string }
        current_price: { type: number }
        result: { type: string, enum: [hit, miss, pending, error] }
        result_details: { type: string }
        confidence: { type: number }

    DailyReport:
      type: object
      properties:
        date: { type: string, format: date }
        total_triggers: { type: integer }
        hits: { type: integer }
        misses: { type: integer }
        accuracy_rate: { type: number }
        triggers:
          type: array
          items:
            type: object
            properties:
              symbol: { type: string }
              description: { type: string }
              result: { type: string }
              price_change: { type: number }

    IndexData:
      type: object
      properties:
        price: { type: number }
        change: { type: number }
        change_percent: { type: number }

    StockMover:
      type: object
      properties:
        symbol: { type: string }
        change_percent: { type: number }
        volume: { type: integer }
```

---

## 5. Jobb/Flöden

### 5.1 Cron-jobb (Tidsbaserade utvärderingar)

```
┌──────────────────────────────────────────────────────────┐
│  DAGLIGT FLÖDE (ET = Eastern Time)                       │
│  svensk tid = ET + 6h                                    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  06:30 ET / 12:30 SE  ┌─────────────────┐               │
│  (30 min före öppning) │ PRE-MARKET      │               │
│                        │ RAPPORT         │               │
│                        │ • Hämta futures  │               │
│                        │ • Lista triggers │               │
│                        │ • Skicka Discord │               │
│                        └────────┬────────┘               │
│                                 │                        │
│  09:30 ET / 15:30 SE  ┌─────────▼─────────┐             │
│  (Marknaden öppnar)   │ MARKET OPEN       │             │
│                       │ • Aktivera alla   │             │
│                       │   triggers        │             │
│                       │ • Starta tracking │             │
│                       └─────────┬─────────┘             │
│                                 │                        │
│  10:30 ET / 16:30 SE  ┌─────────▼─────────┐             │
│  (1 timme efter öpp.) │ FIRST HOUR        │             │
│                       │ EVALUATION        │             │
│                       │ • Utvärdera alla   │             │
│                       │   aktiva triggers  │             │
│                       │ • Skicka rapport   │             │
│                       └─────────┬─────────┘             │
│                                 │                        │
│  13:00 ET / 19:00 SE  ┌─────────▼─────────┐             │
│  (Lunchtid)           │ MID-DAY CHECK     │             │
│                       │ • Uppdatera status │            │
│                       │ • Alerta vid behov  │            │
│                       └─────────┬─────────┘             │
│                                 │                        │
│  16:00 ET / 22:00 SE  ┌─────────▼─────────┐             │
│  (Marknaden stänger)  │ END OF DAY        │             │
│                       │ • Slutlig utvärdering│           │
│                       │ • Generera rapport  │            │
│                       │ • Arkivera triggers │            │
│                       │ • Uppdatera metrics │            │
│                       └─────────────────────┘            │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Event-driven flöden

| Event | Källa | Åtgärd |
|-------|-------|--------|
| Kurs rör sig X% | WebSocket/Pooling | Kontrollera price-triggers |
| Nytt makrodata | API/cron | Utvärdera macro-triggers |
| Användare skapar trigger | MCP API | Aktivera + tracka |
| Trigger träffas | Evaluation Engine | Skicka alert + arkivera |
| Trigger missar | Evaluation Engine | Skicka rapport + arkivera |
| Systemfel | Logger | Skicka error-alert |

### 5.3 Konfiguration (crontab-exempel)

```cron
# Trading Trigger System — Cron-jobb
# Svensk tid (CEST/ET+6)

# 12:30 — Förbörsrapport (30 min före öppning)
30 12 * * 1-5 cd /opt/trading-triggers && python -m triggers.report pre_market

# 15:30 — Marknadsöppning, aktivera triggers
30 15 * * 1-5 cd /opt/trading-triggers && python -m triggers.activate

# 16:30 — First hour evaluation
30 16 * * 1-5 cd /opt/trading-triggers && python -m triggers.evaluate first_hour

# 19:00 — Mid-day check
0 19 * * 1-5 cd /opt/trading-triggers && python -m triggers.evaluate mid_day

# 22:00 — End of day + arkivering
0 22 * * 1-5 cd /opt/trading-triggers && python -m triggers.evaluate eod

# 22:15 — Generera daglig rapport
15 22 * * 1-5 cd /opt/trading-triggers && python -m triggers.report daily

# 22:30 — Uppdatera metrics
30 22 * * 1-5 cd /opt/trading-triggers && python -m triggers.metrics update
```

---

## 6. Tillståndsmaskin

### 6.1 Trigger-livscykel

```
┌─────────┐     create      ┌──────────┐     activate      ┌──────────┐
│  DRAFT  │───────────────►│  ACTIVE  │────────────────►│ TRACKING │
└─────────┘                └──────────┘                 └─────┬──────┘
                                                              │
                    ┌─────────────────────────────────────────┘
                    │
                    │ evaluate
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │   HIT   │ │  MISS   │ │ EXPIRED │
   └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │
        │     ┌─────┘           │
        │     │                 │
        ▼     ▼                 ▼
   ┌──────────────────────────────────────┐
   │            ARCHIVED                  │
   │  (sparas för historik och metrics)  │
   └──────────────────────────────────────┘
```

### 6.2 Tillståndsövergångar

| Från | Till | Trigger | Beskrivning |
|------|------|---------|-------------|
| draft | active | `activate()` | Trigger aktiveras för tracking |
| active | tracking | market_open | Marknaden öppnar, börja tracka |
| tracking | hit | evaluate() | Villkor uppfyllt |
| tracking | miss | evaluate() | Villkor ej uppfyllt, eller motsatt |
| tracking | expired | timeout | Gick utanför tidsfönster |
| hit | archived | archive() | Sparas för historik |
| miss | archived | archive() | Sparas för historik |
| expired | archived | archive() | Sparas för historik |

### 6.3 Tillståndsövergång (i kod)

```python
class TriggerStateMachine:
    VALID_TRANSITIONS = {
        'draft': ['active'],
        'active': ['tracking', 'expired'],
        'tracking': ['hit', 'miss', 'expired'],
        'hit': ['archived'],
        'miss': ['archived'],
        'expired': ['archived'],
        'archived': []  # Terminaltillstånd
    }
    
    def transition(self, trigger: Trigger, new_status: str, reason: str = None):
        current = trigger.status
        if new_status not in self.VALID_TRANSITIONS[current]:
            raise InvalidTransitionError(f"{current} -> {new_status} ej tillåten")
        
        trigger.status = new_status
        trigger.save()
        
        # Logga historik
        TriggerHistory.create(
            trigger_id=trigger.id,
            from_status=current,
            to_status=new_status,
            reason=reason
        )
        
        # Notifiera vid behov
        if new_status in ['hit', 'miss']:
            self.notifier.send_trigger_alert(trigger, new_status)
```

---

## 7. Filstruktur

### 7.1 Mappar och moduler

```
trading-triggers/
├── README.md                          # Projektöversikt och quick-start
├── DESIGN.md                          # Detta dokument
├── requirements.txt                   # Python-beroenden
├── pyproject.toml                     # Modern Python-projektconfig
├── .env.example                       # Miljövariabel-mall
├── .gitignore
│
├── docker/
│   ├── Dockerfile                     # Produktions-image
│   ├── docker-compose.yml             # Hela stacken
│   └── Dockerfile.dev                 # Utvecklings-image
│
├── config/
│   ├── __init__.py
│   ├── settings.py                    # Central konfiguration (Pydantic Settings)
│   ├── stocks.yaml                    # Aktier vi trackar som standard
│   └── triggers/
│       ├── default_rules.yaml         # Standard-trigger-regler
│       └── seasonal_rules.yaml        # Säsongsberoende regler
│
├── src/
│   ├── __init__.py
│   │
│   ├── api/                           # MCP Server (FastAPI)
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI-app entrypoint
│   │   ├── dependencies.py            # Dependency injection
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── triggers.py            # /triggers endpoints
│   │   │   ├── market.py              # /market endpoints
│   │   │   ├── reports.py             # /reports endpoints
│   │   │   └── metrics.py             # /metrics endpoints
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── requests.py            # Pydantic request-modeller
│   │   │   └── responses.py           # Pydantic response-modeller
│   │   └── middleware/
│   │       ├── __init__.py
│   │       ├── rate_limit.py          # Rate limiting
│   │       └── error_handler.py       # Global felhantering
│   │
│   ├── collectors/                    # Data Collection Layer
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract base class
│   │   ├── yahoo_finance.py           # Yahoo Finance-implementation
│   │   ├── alpha_vantage.py           # Alpha Vantage-implementation
│   │   ├── finnhub.py                 # Finnhub WebSocket
│   │   ├── news_api.py                # Nyheter från NewsAPI
│   │   ├── macro_data.py              # FRED/ makrodata
│   │   └── factory.py                 # Factory för collector-val
│   │
│   ├── triggers/                      # Trigger-hantering
│   │   ├── __init__.py
│   │   ├── models.py                  # Trigger-datamodeller (SQLAlchemy)
│   │   ├── manager.py                 # TriggerManager — skapa/aktivera
│   │   ├── evaluator.py               # EvaluationEngine — utvärdera
│   │   ├── state_machine.py           # Tillståndsmaskin
│   │   ├── rules/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Abstract trigger rule
│   │   │   ├── price_rule.py          # PriceTrigger
│   │   │   ├── range_rule.py          # RangeTrigger
│   │   │   ├── momentum_rule.py       # MomentumTrigger
│   │   │   ├── macro_rule.py          # MacroTrigger
│   │   │   └── news_rule.py           # NewsSentimentTrigger
│   │   └── templates/
│   │       ├── __init__.py
│   │       ├── pre_market.py          # Förbörs-template
│   │       └── daily_report.py        # Daglig rapport-template
│   │
│   ├── storage/                       # Databaslager
│   │   ├── __init__.py
│   │   ├── database.py                # Database connection & session
│   │   ├── models.py                  # SQLAlchemy ORM-modeller
│   │   ├── migrations/                # Alembic-migreringar
│   │   │   ├── alembic.ini
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── trigger_repo.py        # Trigger CRUD
│   │       ├── evaluation_repo.py     # Evaluation CRUD
│   │       └── report_repo.py         # Report CRUD
│   │
│   ├── notifications/                  # Notifieringslager
│   │   ├── __init__.py
│   │   ├── base.py                     # Abstract notifier
│   │   ├── discord.py                  # Discord webhook
│   │   ├── email.py                    # Email SMTP
│   │   ├── slack.py                    # Slack webhook
│   │   └── factory.py                  # Factory för notifier-val
│   │
│   ├── scheduler/                      # Cron / jobb-schemaläggning
│   │   ├── __init__.py
│   │   ├── scheduler.py                # APScheduler-wrapper
│   │   ├── jobs/
│   │   │   ├── __init__.py
│   │   │   ├── pre_market_report.py    # Förbörsrapport-jobb
│   │   │   ├── first_hour_eval.py      # First hour evaluation
│   │   │   ├── mid_day_check.py        # Mid-day check
│   │   │   ├── end_of_day.py           # EOD + arkivering
│   │   │   └── daily_metrics.py        # Metrics-uppdatering
│   │   └── cli.py                      # CLI för manuell körning
│   │
│   ├── reports/                        # Rapportgenerering
│   │   ├── __init__.py
│   │   ├── generator.py                # ReportGenerator
│   │   ├── formatters/
│   │   │   ├── __init__.py
│   │   │   ├── markdown.py             # Markdown-rapporter
│   │   │   ├── json.py                 # JSON-rapporter
│   │   │   └── discord_embed.py        # Discord embed-format
│   │   └── templates/
│   │       ├── daily_report.md.j2      # Jinja2-template daglig
│   │       ├── trigger_alert.md.j2     # Trigger alert-template
│   │       └── error_report.md.j2      # Felrapport-template
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging.py                  # Structured logging (structlog)
│   │   ├── retry.py                    # Retry-dekoratörer för API-calls
│   │   ├── cache.py                    # Simple cache (TTL)
│   │   └── validators.py               # Input-validering
│   │
│   └── mcp/                            # MCP (Model Context Protocol) integration
│       ├── __init__.py
│       ├── server.py                   # MCP-server implementation
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── market_tools.py         # marknad-data tools
│       │   ├── trigger_tools.py        # trigger-hantering tools
│       │   └── report_tools.py         # rapport-tools
│       └── prompts/
│           ├── __init__.py
│           └── system_prompt.txt       # System-prompt för MCP
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Pytest fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_trigger_manager.py
│   │   ├── test_evaluator.py
│   │   ├── test_state_machine.py
│   │   ├── test_collectors.py
│   │   └── test_notifiers.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_api_endpoints.py
│   │   ├── test_database.py
│   │   └── test_scheduler.py
│   └── fixtures/
│       ├── sample_triggers.yaml
│       ├── sample_evaluations.yaml
│       └── mock_market_data.json
│
├── scripts/
│   ├── init_db.py                      # Initiera databas
│   ├── seed_stocks.py                  # Seed:a aktie-listan
│   ├── backup_db.py                    # Daglig backup
│   └── health_check.py                 # Hälsokoll för monitoring
│
└── docs/
    ├── architecture.md                 # Arkitektur-dokumentation
    ├── api_reference.md                # API-referens
    ├── deployment.md                   # Deploy-guide
    └── development.md                  # Utvecklingsguide
```

### 7.2 Viktiga filer — snabbreferens

| Fil | Syfte | Vem ändrar |
|-----|-------|------------|
| `src/api/main.py` | FastAPI entrypoint | Dev |
| `src/triggers/manager.py` | Trigger-livscykel | Dev |
| `src/triggers/evaluator.py` | Utvärderingslogik | Dev |
| `config/stocks.yaml` | Vilka aktier vi trackar | Användare |
| `config/triggers/default_rules.yaml` | Trigger-regler | Användare |
| `src/scheduler/jobs/*.py` | Cron-jobb | Dev |
| `src/reports/templates/*.j2` | Rapport-mallar | Dev/Användare |

---

## 8. Teknisk Stack

| Komponent | Teknik | Motivering |
|-----------|--------|------------|
| **Backend** | Python 3.11+ | Mogen, async-support, stort ekosystem |
| **API** | FastAPI | Async-first, auto-docs, Pydantic-integration |
| **Databas** | SQLite → PostgreSQL | Enkel start, skalar till produktion |
| **ORM** | SQLAlchemy 2.0 + Alembic | Standard, migrations-stöd |
| **Scheduler** | APScheduler | Flexibel, cron-syntax, async-stöd |
| **HTTP Client** | httpx | Async, HTTP/2, retries |
| **Config** | Pydantic Settings | Env-vars, validering, defaults |
| **Logging** | structlog + JSON | Structured logs för debugging |
| **Testing** | pytest + pytest-asyncio | Standard, fixtures, async-stöd |
| **Deploy** | Docker + docker-compose | Portabelt, reproducerbart |
| **CI/CD** | GitHub Actions | Automated testing, deploy |

---

## 9. Säkerhet och Begränsningar

### 9.1 Rate Limiting
- Externa API:er: Cache + exponential backoff
- Intern API: 100 req/min per IP
- WebSocket: Max 1 connection per klient

### 9.2 Felhantering
- Retry: Max 3 försök för API-calls
- Fallback: Om Yahoo Finance failar → Alpha Vantage → cached data
- Circuit breaker: Pausa collector vid upprepade fel

### 9.3 Data-lagring
- Personlig data: Ingen (endast publika marknadsdata)
- Loggar: Rensa efter 90 dagar
- Evaluations: Behåll permanent (små dataposter)
- Backups: Daglig backup till S3/lokal disk

---

## 10. Framtida Utökningar (Roadmap)

| Version | Funktion | Beskrivning |
|---------|----------|-------------|
| v1.1 | WebSocket-realtid | Levande kursuppdateringar |
| v1.2 | AI-sentiment | Analysera nyheter med NLP |
| v1.3 | Backtesting | Testa triggers på historisk data |
| v1.4 | Portföljtracking | Koppla till användarens portfölj |
| v1.5 | Alerting-regler | Komplexa villkor (AND/OR/NOT) |
| v2.0 | Dashboard | Webb-GUI för trigger-hantering |

---

## Sammanfattning

Detta system är designat för att vara **enkelt att starta** (SQLite + filbaserad config) men **skalbart till produktion** (PostgreSQL + Docker + CI/CD). Arkitekturen separerar tydligt mellan data-insamling, trigger-hantering, utvärdering och rapportering, vilket gör det lätt att testa, underhålla och utöka.

**Nästa steg:** Implementera komponenterna i prioritetsordning:
1. Market Data Collector + Storage
2. Trigger Manager + State Machine
3. Evaluation Engine
4. MCP API Server
5. Notifier (Discord)
6. Scheduler/Cron-jobb
