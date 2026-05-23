## Teknisk kravställare — Sammanfattning

**Projekt:** valvet-trading-triggers  
**Arkitektur:** MCP-server med Python/FastAPI + Celery för schemaläggning

### Föreslagen stack
- **Python 3.12+** — kärnspråk med starkt finansiellt ekosystem
- **FastAPI** — async API för MCP-server och REST
- **SQLite → PostgreSQL** — databas (enkel start, migrerbar)
- **Redis + Celery** — cache och schemaläggning av trigger-evalueringar
- **yfinance** — primär datakälla (gratis, ingen API-nyckel)
- **Alpha Vantage/Polygon** — fallback vid blockering

### MCP-server capabilities
- **Resources:** dagliga triggers, historik, marknadsstatus, watchlist
- **Tools:** utvärdera trigger, hämta aktiekurs, kör daglig analys, hantera watchlist

### Dataflöde
1. **13:00** — Generera förbörsrapport (triggers för dagen)
2. **15:30** — Utvärdera opening range
3. **16:30** — First hour-evaluering + Discord-notifiering
4. **22:00** — End of day-sammanfattning

### Deployment
- **Fas 1:** Kör lokalt på Mac minin (Docker Compose)
- **Fas 2:** Fly.io/Railway vid behov

### Säkerhet
- API-nycklar i `.env` (gitignore:ad)
- Rate limiting per provider med exponentiell backoff
- Circuit breaker vid upprepade fel

### CI/CD
- GitHub-repo: `valvet-trading-triggers`
- GitHub Actions: test → type check → lint → deploy
- Coverage-mål: 80%+ på core-logic

### Felhantering
- Exponentiell backoff med 3 försök
- Fallback-kedja: Yahoo → Alpha Vantage → Polygon
- Circuit breaker (5 fel på 1 min → 5 min paus)
- Strukturerad loggning (INFO/WARNING/ERROR/CRITICAL)

**Status:** Klar för design-review
