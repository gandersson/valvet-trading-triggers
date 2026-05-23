# Kravspecifikation: Trading Trigger System (TTS)

## 1. Översikt

### 1.1 Bakgrund
Systemet ska automatiskt hämta aktiekurser för US-marknaden och utvärdera fördefinierade "triggers" — villkor baserade på pris, volym, rörelser över/under öppningskurs, etc. Utvärdering sker efter första timmen av US-handeln (ca 16:30 svensk tid) och resultat lagras för historisk analys.

### 1.2 Mål
- Automatisera daglig trigger-utvärdering utan manuell övervakning
- Erbjuda ett MCP-server-interface för interaktiva frågor
- Bygga historisk databas över triggers och deras träffsäkerhet

### 1.3 Omfattning
- **In-Scope:** US-aktier (NYSE, NASDAQ), realtidskurser, trigger-utvärdering, historik, Discord-notifieringar, MCP-server
- **Out-of-Scope:** Handel/utförande, options, krypto, icke-US marknader

---

## 2. Datakällor

### 2.1 Primära källor
| Källa | Data | Kostnad | API |
|-------|------|---------|-----|
| **Yahoo Finance** | Realtidskurser, volym, öppningskurs, dagshög/låg | Gratis (ostabil) | `yfinance` (Python) |
| **Alpha Vantage** | Realtidskurser, intradag, historik | Freemium (5 req/min) | REST API |
| **Polygon.io** | Realtidskurser, aggregates, tick-level | Betald (~$49/mån) | REST/WebSocket |
| **IEX Cloud** | Realtidskurser, intradag, stats | Freemium | REST API |

### 2.2 Reservkällor
- Finnhub (gratis tier: 60 req/min)
- Twelve Data (gratis tier: 8 req/min)
- Marketwatch/Investing.com scraping (om API misslyckas)

### 2.3 Data att hämta per aktie
- [x] Nuvarande pris
- [x] Öppningskurs
- [x] Dagshögsta / dagslägsta
- [x] Volym (nuvarande + genomsnittlig)
- [x] Föregående dags stängning
- [x] Pre-market data (om tillgängligt)
- [x] 1h / 2h / EOD-priser för utvärdering

---

## 3. Triggertyper

### 3.1 Prisbaserade triggers
| Trigger | Beskrivning | Exempel |
|---------|-------------|---------|
| **Open_Above** | Pris > öppningskurs efter 1h | NVDA > $220.90 |
| **Open_Below** | Pris < öppningskurs efter 1h | WMT < $121.24 |
| **Premarket_Break** | Bryter premarket-high/low | TTWO > $245 |
| **Day_High_Break** | Bryter dags högst under sessionen | — |
| **Support_Hold** | Håller sig över stödnivå | ENPH > $60 |

### 3.2 Volymbaserade triggers
| Trigger | Beskrivning |
|---------|-------------|
| **High_Volume** | Volym > 1.5x genomsnittlig volym efter 1h |
| **Volume_Spike** | Plötslig volymökning > 2x inom 5 min |

### 3.3 Rörelsebaserade triggers
| Trigger | Beskrivning |
|---------|-------------|
| **Strong_First_Hour** | >+1% efter 1h med ökande volym |
| **Weak_First_Hour** | <-1% efter 1h med ökande volym |
| **Mean_Reversion** | Snabb rörelse (>3%) åt ett håll, sedan vändning |

### 3.4 Marknadsbaserade triggers
| Trigger | Beskrivning |
|---------|-------------|
| **Index_Alignment** | Aktie rör sig i linje med S&P 500/Nasdaq |
| **Sector_Leadership** | Aktie överpresterar sin sektor |

### 3.5 Makro-triggers (manuella)
| Trigger | Beskrivning |
|---------|-------------|
| **Yield_Direction** | 10Y-räntans riktning under första 1–2 timmarna |
| **Oil_Movement** | Oljeprisvolatilitet intradag |
| **News_Event** | Stora nyheter under sessionen |

---

## 4. Automatiska utvärderingar

### 4.1 Tidsplan (svensk tid / ET)
| Utvärdering | Tid (CET) | Tid (ET) | Beskrivning |
|-------------|-----------|----------|-------------|
| **Pre-market** | 13:30 | 07:30 | Hämta premarket-data, generera trigger-lista |
| **1h Check** | 16:35 | 10:35 | Utvärdera alla aktie-triggers efter 1h |
| **2h Check** | 17:35 | 11:35 | Uppdatera utvärdering efter 2h |
| **EOD Check** | 23:00 | 17:00 | Slutlig utvärdering vid stängning |

### 4.2 Processflöde
```
1. [Cron: 13:30 CET] → Hämta premarket-data → Generera dagens triggers
2. [Cron: 16:35 CET] → Hämta 1h-priser → Utvärdera triggers → Spara resultat
3. [Cron: 17:35 CET] → Hämta 2h-priser → Uppdatera utvärdering
4. [Cron: 23:00 CET] → Hämta EOD-priser → Slutlig utvärdering → Beräkna stats
5. [Discord/MCP] → Notifiera / Svara på förfrågningar
```

### 4.3 Retry-logik
- Om API misslyckas: vänta 30s, retry max 3 gånger
- Om fortfarande fel: använd reservkälla
- Om alla källor misslyckas: logga fel, skicka varning, försök vid nästa schemalagda körning

---

## 5. MCP-Server Interface

### 5.1 Översikt
En MCP-server som exponerar tools för Claude/andra AI-agenter att ställa frågor om triggers.

### 5.2 Tools/Commands

#### `get_todays_triggers()`
```typescript
{
  name: "get_todays_triggers",
  description: "Hämta dagens aktiva triggers och deras status",
  parameters: {
    type: "object",
    properties: {
      filter: {
        type: "string",
        enum: ["all", "pending", "hit", "miss", "mixed"],
        default: "all"
      }
    }
  }
}
```

#### `get_trigger_result()`
```typescript
{
  name: "get_trigger_result",
  description: "Hämta resultat för specifik trigger/aktie idag",
  parameters: {
    type: "object",
    properties: {
      symbol: { type: "string", description: "Aktiesymbol, t.ex. NVDA" },
      evaluation_time: {
        type: "string",
        enum: ["1h", "2h", "eod"],
        default: "latest"
      }
    },
    required: ["symbol"]
  }
}
```

#### `get_historical_accuracy()`
```typescript
{
  name: "get_historical_accuracy",
  description: "Hämta historisk träffsäkerhet för triggers",
  parameters: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      trigger_type: { type: "string" },
      days: { type: "integer", default: 30 },
      date_range: {
        type: "object",
        properties: {
          from: { type: "string", format: "date" },
          to: { type: "string", format: "date" }
        }
      }
    }
  }
}
```

#### `get_market_summary()`
```typescript
{
  name: "get_market_summary",
  description: "Hämta dagens marknadssammanfattning (index, räntor, olja)",
  parameters: {
    type: "object",
    properties: {}
  }
}
```

#### `add_trigger()`
```typescript
{
  name: "add_trigger",
  description: "Lägg till ny trigger för utvärdering",
  parameters: {
    type: "object",
    properties: {
      symbol: { type: "string", required: true },
      trigger_type: { type: "string", required: true },
      condition: { type: "string", required: true },
      source: { type: "string", description: "Varför triggern skapades" },
      evaluation_times: {
        type: "array",
        items: { type: "string", enum: ["1h", "2h", "eod"] },
        default: ["1h", "eod"]
      }
    },
    required: ["symbol", "trigger_type", "condition"]
  }
}
```

### 5.3 Exempel på frågor MCP-servern ska besvara
- "Vilka är dagens intressanta aktier?"
- "Hur gick triggers idag?"
- "Vilka triggers har bäst träffsäkerhet senaste 30 dagarna?"
- "Hur har NVDA presterat på Open_Above-triggers?"
- "Vad var dagens marknadssammanfattning?"

---

## 6. Persistens och Historik

### 6.1 Databas
**SQLite** (initialt, enkelt att migrera till PostgreSQL senare)

### 6.2 Tabeller

#### `triggers`
| Kolumn | Typ | Beskrivning |
|--------|-----|-------------|
| id | INTEGER PK | Unikt ID |
| date | DATE | Datum |
| symbol | TEXT | Aktiesymbol |
| trigger_type | TEXT | Typ av trigger |
| condition | TEXT | Villkor (t.ex. "price > open") |
| source | TEXT | Ursprung (t.ex. "premarket_report", "manual") |
| created_at | TIMESTAMP | Skapad tid |

#### `evaluations`
| Kolumn | Typ | Beskrivning |
|--------|-----|-------------|
| id | INTEGER PK | Unikt ID |
| trigger_id | INTEGER FK | Ref till triggers |
| evaluation_time | TEXT | "1h", "2h", "eod" |
| price_at_eval | REAL | Pris vid utvärdering |
| open_price | REAL | Öppningskurs |
| result | TEXT | "hit", "miss", "mixed", "pending" |
| accuracy_score | REAL | 0.0–1.0 (gradvis träff) |
| evaluated_at | TIMESTAMP | Utvärderingstid |

#### `market_data`
| Kolumn | Typ | Beskrivning |
|--------|-----|-------------|
| id | INTEGER PK | Unikt ID |
| date | DATE | Datum |
| sp500_open | REAL | S&P 500 öppning |
| sp500_1h | REAL | S&P 500 efter 1h |
| sp500_eod | REAL | S&P 500 stängning |
| nasdaq_open | REAL | Nasdaq öppning |
| nasdaq_eod | REAL | Nasdaq stängning |
| yield_10y | REAL | 10Y-ränta |
| oil_wti | REAL | WTI oljepris |
| vix | REAL | VIX-index |

#### `historical_stats`
| Kolumn | Typ | Beskrivning |
|--------|-----|-------------|
| id | INTEGER PK | Unikt ID |
| symbol | TEXT | Aktiesymbol |
| trigger_type | TEXT | Typ av trigger |
| total_count | INTEGER | Antal utvärderingar |
| hit_count | INTEGER | Antal träffar |
| miss_count | INTEGER | Antal missar |
| hit_rate | REAL | Träffsäkerhet (%) |
| avg_return_hit | REAL | Genomsnittlig avkastning vid träff |
| avg_return_miss | REAL | Genomsnittlig avkastning vid miss |
| last_updated | TIMESTAMP | Senast uppdaterad |

### 6.3 Dataretention
- Rådata: 90 dagar
- Utvärderingar: Permanent
- Historisk stats: Permanent, uppdateras dagligen
- Marknadsdata: Permanent

---

## 7. Notifieringar

### 7.1 Discord
| Händelse | Tid | Innehåll |
|----------|-----|----------|
| Dagens triggers genererade | ~13:45 | Lista med dagens aktier och triggers |
| 1h-resultat klart | ~16:40 | Sammanfattning: X träff, Y miss |
| 2h-uppdatering | ~17:40 | Uppdaterad status |
| EOD-sammanfattning | ~23:05 | Fullständig dagssammanfattning + veckostats |
| Fel/varning | Omedelbart | Om API misslyckas eller data saknas |

### 7.2 Email (valfritt)
- Daglig EOD-sammanfattning
- Veckorapport med träffsäkerhetsstatistik
- Varning vid kritiska fel

### 7.3 Format (Discord)
```markdown
**📊 Trigger-rapport: 1h (22 maj 2026)**

| Aktie | Trigger | Öppning | Nu | Resultat |
|-------|---------|---------|----|----------|
| NVDA | Open_Above | $220.90 | $217.23 | ❌ Miss |
| ENPH | Momentum | $62.48 | $64.01 | ✅ Hit |

**Sammanfattning:** 1/5 träff (20%)
```

---

## 8. Integrationer

### 8.1 Existerande system
- **Discord:** Marvin (denna bot) ska kunna fråga MCP-servern och posta resultat
- **GitHub:** Versionshantering, CI/CD, issues
- **OpenClaw:** Cron-jobb, miljövariabler, secrets

### 8.2 Externa integrationer
- **Yahoo Finance API:** Primär datakälla
- **Discord Webhooks:** För notifieringar
- **SMTP (valfritt):** För email-notifieringar

---

## 9. Arkitektur

### 9.1 Komponenter
```
┌─────────────────────────────────────────────┐
│           Trading Trigger System              │
├─────────────────────────────────────────────┤
│                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  Data    │  │ Trigger  │  │   MCP    │  │
│  │ Fetcher  │→ │ Engine   │→ │  Server  │  │
│  │ (Python) │  │ (Python) │  │ (Python) │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│        ↓              ↓              ↓      │
│  ┌──────────────────────────────────────┐   │
│  │           SQLite Database             │   │
│  └──────────────────────────────────────┘   │
│        ↓                                    │
│  ┌──────────┐  ┌──────────┐               │
│  │ Discord  │  │  Stats   │               │
│  │ Notifier │  │ Reporter │               │
│  └──────────┘  └──────────┘               │
│                                               │
└─────────────────────────────────────────────┘
```

### 9.2 Teknisk stack
| Komponent | Teknik |
|-----------|--------|
| Huvudspråk | Python 3.11+ |
| API/Data | `yfinance`, `requests`, `aiohttp` |
| Databas | SQLite (→ PostgreSQL) |
| MCP Server | `mcp` (Python SDK) |
| Scheduling | `APScheduler` eller cron + `systemd` |
| Konfiguration | YAML/JSON |
| Logs | `structlog` + filrotation |

---

## 10. Utvecklingsplan

### 10.1 Faser

#### Fas 1: MVP (vecka 1–2)
- [ ] Hämta aktiekurser från Yahoo Finance
- [ ] Utvärdera 5 enkla triggers efter 1h
- [ ] Spara resultat i SQLite
- [ ] Discord-notifiering med enkel sammanfattning

#### Fas 2: MCP + Historik (vecka 3–4)
- [ ] MCP-server med grundläggande tools
- [ ] Historisk statistik-beräkning
- [ ] Utvärdering efter 2h och EOD

#### Fas 3: Avancerat (vecka 5–6)
- [ ] Fler trigger-typer (volym, sektorer)
- [ ] Reservdatakällor
- [ ] Email-notifieringar
- [ ] Förbättrad felhantering

#### Fas 4: Produktion (vecka 7–8)
- [ ] PostgreSQL-migration
- [ ] Docker-containerisering
- [ ] CI/CD-pipeline (GitHub Actions)
- [ ] Dokumentation

### 10.2 GitHub-repo
```
trading-triggers/
├── src/
│   ├── __init__.py
│   ├── data_fetcher.py      # Hämta kurser
│   ├── trigger_engine.py    # Utvärdera triggers
│   ├── database.py          # SQLite/DB-hantering
│   ├── mcp_server.py        # MCP-server
│   ├── discord_notifier.py  # Discord-meddelanden
│   └── config.py            # Konfiguration
├── tests/
├── scripts/
│   ├── run_premarket.py     # 13:30 CET
│   ├── run_1h_eval.py       # 16:35 CET
│   ├── run_2h_eval.py       # 17:35 CET
│   └── run_eod.py           # 23:00 CET
├── config/
│   └── triggers.yaml        # Trigger-definitioner
├── requirements.txt
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 11. Säkerhet

- [ ] API-nycklar i miljövariabler (inte i kod)
- [ ] Rate-limiting mot datakällor
- [ ] Ingen handelsinformation lagras
- [ ] Loggar innehåller inga personuppgifter
- [ ] Discord-tokens hanteras säkert

---

## 12. Framgångsmått

| Mått | Målvärde | Mätning |
|------|----------|---------|
| Trigger-utvärderingar/dag | 100% | Antal dagar med komplett data |
| API-tillgänglighet | >95% | Uptime för datahämtning |
| Discord-notifieringar | <2min delay | Tid från utvärdering till post |
| Historisk täckning | >90% | Andel dagar med sparad data |
| Träffsäkerhet | Spåras | Hit-rate per trigger-typ |

---

## 13. Definitioner

| Term | Definition |
|------|------------|
| **Trigger** | Fördefinierat villkor som utvärderas mot aktiekursdata |
| **Hit** | Villkoret uppfylls |
| **Miss** | Villkoret uppfylls inte |
| **Mixed** | Villkoret delvis uppfyllt (används vid gradvis utvärdering) |
| **1h/2h/EOD** | 1 timme / 2 timmar / End of Day efter marknadsöppning |
| **CET** | Central European Time (svensk tid) |
| **ET** | Eastern Time (US-marknadstid) |

---

*Senast uppdaterad: 2026-05-22*
*Version: 1.0*
*Ansvarig: Trading Trigger System Team*
