# Trading Trigger System — Technical Specification

**Version:** 1.0  
**Date:** 2026-05-22  
**Author:** Technical Requirements Subagent  
**Project:** valvet-trading-triggers

---

## 1. Teknisk Stack

### Rekommenderad stack

| Komponent | Val | Motivering |
|-----------|-----|------------|
| **Språk** | Python 3.12+ | Bra ekosystem för finansiell data (yfinance, pandas, numpy), stark MCP-SDK-support |
| **Framework** | FastAPI (ASGI) | Högpresterande async API, auto-docs (Swagger), serverar statiskt chattgränssnitt på `/chat` |
| **Databas** | SQLite (lokal/dev) → PostgreSQL (prod) | Enkel start, migrerbar till PostgreSQL vid skalning |
| **Cache** | Redis | Realtids-cachning av aktiekurser, rate limit tracking |
| **Task Queue** | Celery + Redis | Schemalagda jobb (förbörsrapport, trigger-evaluering efter 1h/2h/EOD) |
| **Scheduler** | Celery Beat | Cron-liknande schemaläggning utan externa beroenden |

### Befintliga gränssnitt

| Gränssnitt | URL/Transport | Beskrivning |
|-----------|---------------|-------------|
| **REST API** | `http://127.0.0.1:8000` | FastAPI med Swagger på `/docs` |
| **Chattgränssnitt** | `http://127.0.0.1:8000/chat` | Single-page app (vanilla HTML/CSS/JS), svenska kommandon |
| **MCP-server** | stdio | AI-assistentintegration (Claude, Cursor) |
| **CLI** | `python src/trigger_system_v1.py` | Terminal-baserad körning |
| **Discord** | webhook | Automatiska push-rapporter |

### Alternativ beaktade

- **Node.js/TypeScript**: Bra MCP-support men sämre finansiellt ekosystem
- **Go**: Snabbare men längre utvecklingstid för dataanalys
- **DuckDB**: Bra för analytiska queries men sämre för concurrent writes

---

## 2. MCP-Server Specifikation

### Resources (read-only data)

```
resource://triggers/daily/{date}       → Dagens aktiva triggers
resource://triggers/history/{symbol}  → Trigger-historik för specifik aktie
resource://market/status               → Nuvarande marknadsstatus (öppen/stängd)
resource://stocks/watchlist            → Bevakningslista med trigger-konfiguration
```

### Tools (actions)

```
tool: evaluate_trigger
  input: { symbol: string, trigger_type: string, parameters: object }
  output: { triggered: boolean, confidence: float, details: object }

tool: get_stock_quote
  input: { symbol: string }
  output: { price: float, change_pct: float, volume: int, timestamp: string }

tool: run_daily_analysis
  input: { date?: string (optional, default today) }
  output: { report: string, triggers_evaluated: int, hits: int, misses: int }

tool: add_to_watchlist
  input: { symbol: string, trigger_config: object }
  output: { success: boolean, watchlist_id: string }

tool: get_trigger_history
  input: { symbol?: string, date_from?: string, date_to?: string }
  output: { history: Array<TriggerResult> }
```

### Input/Output Schemas (Pydantic)

```python
class TriggerConfig(BaseModel):
    symbol: str
    trigger_type: Literal["opening_range", "price_level", "momentum", "gap_fill"]
    parameters: dict  # trigger-specifika parametrar
    alert_threshold: float = 0.02  # 2% tolerance

class TriggerResult(BaseModel):
    symbol: str
    trigger_type: str
    triggered: bool
    confidence: float  # 0.0 - 1.0
    entry_price: Optional[float]
    exit_price: Optional[float]
    timestamp: datetime
    details: dict
```

---

## 3. API-Integrationer

### Primär datakälla: Yahoo Finance (via `yfinance`)

```python
# Gratis, ingen API-nyckel krävs
import yfinance as yf

ticker = yf.Ticker("NVDA")
hist = ticker.history(period="1d", interval="1m")
```

**Fördelar:**
- Ingen API-nyckel
- Realtidsdata (15 min fördröjning för gratiskonton)
- Historisk data tillbaka till 1970
- Stöd för svenska aktier (flera marknader)

**Nackdelar:**
- Oofficiellt API — kan brytas
- Rate limits (oklara, men aggressiva vid överanvändning)
- Ingen garanti för tillgänglighet

### Sekundär datakälla: Alpha Vantage

```
https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=NVDA&interval=1min&apikey=XXX
```

**Fördelar:**
- Officiellt API med SLA
- 25 gratis calls/dag, $49.99/mån för 75 calls/min

**Nackdelar:**
- Kräver API-nyckel
- Långsammare rate limits på gratisnivån

### Backup: Polygon.io

```
https://api.polygon.io/v2/aggs/ticker/NVDA/range/1/minute/2026-05-22/2026-05-22
```

**Fördelar:**
- Mycket tillförlitligt
- 5 API-calls/min gratis

**Nackdelar:**
- Kräver API-nyckel
- Begränsad historisk data på gratisnivån

### Implementeringsstrategi

```python
class DataProvider(ABC):
    async def get_intraday_data(self, symbol: str, interval: str) -> DataFrame:
        ...

class YahooFinanceProvider(DataProvider):
    # Primär, gratis
    
class AlphaVantageProvider(DataProvider):
    # Fallback om Yahoo blockar
    
class PolygonProvider(DataProvider):
    # Tertiär fallback
```

---

## 4. Dataflöde och Pipeline

### Översikt

```
┌─────────────────────────────────────────────────────────────┐
│                     DATAKÄLLOR                              │
│  Yahoo Finance    Alpha Vantage    Polygon.io              │
└──────────┬────────────────┬────────────────┬───────────────┘
           │                │                │
           └────────────────┴────────────────┘
                            │
                   ┌─────────▼──────────┐
                   │  Data Ingestion     │  ← Celery task var 15e min
                   │  (fetch_prices.py)  │
                   └─────────┬───────────┘
                             │
                   ┌─────────▼──────────┐
                   │  Price Cache        │  ← Redis (TTL 5 min)
                   │  (prices:{symbol})  │
                   └─────────┬───────────┘
                             │
                   ┌─────────▼──────────┐
                   │  Trigger Engine     │  ← Celery task vid marknadsöppning
                   │  (evaluate.py)      │    + efter 1h, 2h, EOD
                   └─────────┬───────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌─────────┐   ┌─────────┐   ┌─────────────┐
        │ SQLite  │   │ Redis   │   │ Notifications│
        │ (hist)  │   │ (cache) │   │ (Discord)    │
        └─────────┘   └─────────┘   └─────────────┘
```

### Detaljerat flöde

#### Steg 1: Pre-market (13:00 svensk tid / 07:00 ET)
- Celery task kör `generate_premarket_report()`
- Hämtar overnight data, futures, nyheter
- Genererar trigger-lista (som idag manuellt)
- Sparar till databas: `daily_triggers`

#### Steg 2: Market Open (15:30 svensk tid / 09:30 ET)
- Celery task kör `evaluate_opening_triggers()`
- Hämtar opening prices
- Utvärderar triggers mot opening range
- Uppdaterar `trigger_results` med initial status

#### Steg 3: First Hour (16:30 svensk tid / 10:30 ET)
- Celery task kör `evaluate_first_hour()`
- Hämtar 1h-data
- Utvärderar alla triggers
- Sparar resultat + skickar Discord-notifiering

#### Steg 4: End of Day (22:00 svensk tid / 16:00 ET)
- Celery task kör `evaluate_eod()`
- Slutlig utvärdering
- Genererar daglig sammanfattning
- Sparar till `trigger_history`

---

## 5. Deployment-Strategi

### Fas 1: Lokal utveckling

```bash
# Kör direkt på Mac mini
python -m uvicorn main:app --host 0.0.0.0 --port 8000
redis-server  # cache
celery -A tasks worker --loglevel=info  # workers
celery -A tasks beat --loglevel=info    # scheduler
```

### Fas 2: Containerisering

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///data/trading.db
      - REDIS_URL=redis://redis:6379
  redis:
    image: redis:7-alpine
  celery_worker:
    build: .
    command: celery -A tasks worker --loglevel=info
  celery_beat:
    build: .
    command: celery -A tasks beat --loglevel=info
```

### Fas 3: Cloud (om behov uppstår)

- **Fly.io** eller **Railway** för enkel Python-deployment
- **Render** för gratis hosting med cron-jobs
- **AWS ECS** om skalning krävs

**Rekommendation:** Börja med Docker Compose på Mac minin, migrera till cloud vid behov.

---

## 6. Säkerhetskrav

### API-nyckelhantering

```python
# .env (gitignore-ad!)
YAHOO_FINANCE_ENABLED=true
ALPHA_VANTAGE_API_KEY=av_xxx...
POLYGON_API_KEY=poly_xxx...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Rate Limiting

| Provider | Limit | Strategi |
|----------|-------|----------|
| Yahoo Finance | Oklart (unofficial) | Exponentiell backoff, max 100 calls/min |
| Alpha Vantage | 25/dag (gratis) | Prioritera, använd endast som fallback |
| Polygon | 5/min (gratis) | Queue-baserad throttle |

```python
class RateLimiter:
    def __init__(self, provider: str, max_calls: int, window: int):
        self.provider = provider
        self.redis = redis.Redis()
    
    async def acquire(self) -> bool:
        key = f"rate_limit:{self.provider}"
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, self.window)
        return current <= self.max_calls
```

### Autentisering

- **MCP-server:** Ingen auth initialt (kör lokalt)
- **Vid cloud-deployment:** API-nyckel eller JWT
- **Discord-webhook:** URL-baserad auth (skydda URL:en!)

---

## 7. Teststrategi

### Enhetstester (pytest)

```python
# tests/test_trigger_engine.py
@pytest.mark.parametrize("symbol,trigger_type,expected", [
    ("NVDA", "opening_range", True),   # Gap up
    ("WMT", "momentum", False),        # Sidledes
])
def test_trigger_evaluation(symbol, trigger_type, expected):
    result = engine.evaluate(symbol, trigger_type, mock_data)
    assert result.triggered == expected
```

**Mål:** 80%+ coverage på core-logic (trigger engine, data providers)

### Integrationstester

```python
# tests/test_data_pipeline.py
@pytest.mark.asyncio
async def test_full_pipeline():
    # 1. Hämta data
    data = await provider.get_intraday_data("NVDA", "1m")
    # 2. Utvärdera trigger
    result = engine.evaluate("NVDA", "opening_range", data)
    # 3. Spara resultat
    await db.save_trigger_result(result)
    # 4. Verifiera
    saved = await db.get_trigger_result("NVDA", today)
    assert saved == result
```

### Mock-strategi

- **Yahoo Finance:** VCR.py eller responses-biblioteket
- **Discord:** Mock-webhook eller test-kanal
- **Redis:** fakeredis

---

## 8. Versionshantering och CI/CD

### GitHub-repo: `valvet-trading-triggers`

```
.gitignore:
.env
*.db
data/
__pycache__/
.pytest_cache/
```

### Branch-strategi

- `main` — produktionskod
- `dev` — utveckling
- `feature/*` — funktioner
- `hotfix/*` — kritiska buggar

### GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest --cov=src --cov-report=xml
      - run: mypy src/  # type checking
      - run: ruff check src/  # linting
```

### Deployment (vid cloud)

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Fly.io
        run: |
          flyctl deploy --remote-only
```

---

## 9. Konfiguration och Miljövariabler

### `.env` (exempel)

```bash
# Database
DATABASE_URL=sqlite:///data/trading.db
# DATABASE_URL=postgresql://user:pass@localhost/trading

# Cache
REDIS_URL=redis://localhost:6379/0

# API Keys
ALPHA_VANTAGE_API_KEY=
POLYGON_API_KEY=

# Notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
NOTIFY_ON_TRIGGER=true

# Scheduler
TIMEZONE=Europe/Stockholm
MARKET_OPEN=09:30
MARKET_CLOSE=16:00

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/trading.log
```

### Konfigurationshierarki (prioritet)

1. Miljövariabler
2. `.env`-fil
3. `config.yaml`
4. Default-värden i kod

---

## 10. Felhantering och Återförsök

### Exponentiell backoff

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((ConnectionError, RateLimitError))
)
async def fetch_stock_data(symbol: str) -> DataFrame:
    return await provider.get_intraday_data(symbol)
```

### Fallback-kedja

```python
async def get_data_with_fallback(symbol: str) -> DataFrame:
    providers = [YahooFinanceProvider(), AlphaVantageProvider(), PolygonProvider()]
    for provider in providers:
        try:
            return await provider.get_intraday_data(symbol)
        except Exception as e:
            logger.warning(f"{provider.name} failed: {e}")
            continue
    raise AllProvidersFailedError(f"No data available for {symbol}")
```

### Circuit Breaker

```python
# Om en provider misslyckas 5 gånger på 1 minut, pausa i 5 min
class CircuitBreaker:
    def __init__(self, threshold=5, timeout=300):
        self.threshold = threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure = None
    
    def can_execute(self) -> bool:
        if self.failures >= self.threshold:
            if time.time() - self.last_failure < self.timeout:
                return False
            self.failures = 0  # Reset
        return True
```

### Loggning och alerting

- **INFO:** Normal drift (trigger-evalueringar, data-hämtning)
- **WARNING:** Rate limits nära, fallback aktiverat
- **ERROR:** Alla providers misslyckade, Discord-alert
- **CRITICAL:** MCP-server nere, manuell intervention krävs

---

## Appendix A: Databasschema

```sql
-- triggers
create table daily_triggers (
    id integer primary key,
    date date not null,
    symbol text not null,
    trigger_type text not null,
    parameters json,
    created_at timestamp default current_timestamp
);

-- trigger_results
create table trigger_results (
    id integer primary key,
    trigger_id integer references daily_triggers(id),
    evaluated_at timestamp,
    triggered boolean,
    confidence float,
    entry_price float,
    exit_price float,
    details json
);

-- price_data (optional, för backtesting)
create table price_data (
    id integer primary key,
    symbol text not null,
    timestamp timestamp not null,
    open float,
    high float,
    low float,
    close float,
    volume integer
);

-- performance metrics
create table trigger_performance (
    id integer primary key,
    symbol text,
    trigger_type text,
    total_evaluated int,
    hits int,
    misses int,
    avg_confidence float,
    period_start date,
    period_end date
);
```

## Appendix B: MCP-Server Manifest

```json
{
  "name": "valvet-trading-triggers",
  "version": "1.0.0",
  "description": "Real-time stock trigger evaluation and market analysis",
  "resources": [
    "triggers/daily/{date}",
    "triggers/history/{symbol}",
    "market/status",
    "stocks/watchlist"
  ],
  "tools": [
    "evaluate_trigger",
    "get_stock_quote",
    "run_daily_analysis",
    "add_to_watchlist",
    "get_trigger_history"
  ],
  "transport": "stdio"
}
```
