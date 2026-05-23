# Trading Triggers — Webhook Setup

## Sammanfattning

Discord-webhook för automatiska trigger-rapporter från trading-triggers-systemet är nu konfigurerad och aktiv.

---

## 📋 Konfigurationsdetaljer

### Webhook URL
- **URL:** `https://discord.com/api/webhooks/1507670079159009361/TtYim856aiFAV-626MYCtMGln12x4QpJcrRNb4DjQicSMLga4lzn1nFRVAvFtrKiOnBk`
- **Discord-kanal:** `#trading-triggers` (ID: `1507416330415116381`)
- **Skapad:** 2026-05-23 av Göran
- **Bot:** Marvin (OpenClaw)

### Tidsinställning
- **Kör:** Varje vardag (måndag–fredag)
- **Tider:**
  - **1h:** Kl 16:35 CET (10:35 EST)
  - **2h:** Kl 18:35 CET (12:35 EST)
  - **EOD:** Kl 23:00 CET (17:00 EST)
- **Alternativ körning:** Kan också köras manuellt med `run_with_webhook.sh`

---

## 📁 Projektstruktur

```
projects/trading-triggers/
├── src/
│   ├── trigger_system_v1.py      # Huvudkod (V1)
│   └── poc_trigger_system.py     # Proof-of-concept
├── run_with_webhook.sh           # Wrapper med webhook-URL
├── run_daily.sh                  # LaunchAgent-script
├── test_webhook.py               # Test-script för webhook
├── data/
│   └── triggers.db               # SQLite-databas
├── .venv/                        # Python virtual environment
├── requirements.txt              # Python-beroenden
├── README.md                     # Dokumentation
└── .github/                      # GitHub-templates

# Lokal installation (macOS LaunchAgent)
~/Library/LaunchAgents/
└── se.xandgo.trading-triggers.plist   # macOS schemaläggare
```

---

## 🛠️ Installerade filer

### 1. Kör-script: `run_with_webhook.sh`
```bash
#!/bin/bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
source .venv/bin/activate
python src/trigger_system_v1.py
```

### 2. LaunchAgent: `se.xandgo.trading-triggers.plist`

**Varför LaunchAgent och inte cron?**
- Cron kunde inte laddas på macOS (Input/output error — troligen TCC/behörighetsproblem)
- LaunchAgent är dessutom mer Mac-vänligt och integreras bättre med systemet

**Plats:** `~/Library/LaunchAgents/se.xandgo.trading-triggers.plist`

**Innehåll:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>se.xandgo.trading-triggers</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/xandgo/.openclaw/workspace/projects/trading-triggers/run_daily.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <!-- ========== 1h utvärdering (16:35 CET) ========== -->
        <!-- Måndag -->
        <dict>
            <key>Weekday</key><integer>1</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Tisdag -->
        <dict>
            <key>Weekday</key><integer>2</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Onsdag -->
        <dict>
            <key>Weekday</key><integer>3</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Torsdag -->
        <dict>
            <key>Weekday</key><integer>4</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Fredag -->
        <dict>
            <key>Weekday</key><integer>5</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        
        <!-- ========== 2h utvärdering (18:35 CET) ========== -->
        <!-- Måndag -->
        <dict>
            <key>Weekday</key><integer>1</integer>
            <key>Hour</key><integer>18</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Tisdag -->
        <dict>
            <key>Weekday</key><integer>2</integer>
            <key>Hour</key><integer>18</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Onsdag -->
        <dict>
            <key>Weekday</key><integer>3</integer>
            <key>Hour</key><integer>18</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Torsdag -->
        <dict>
            <key>Weekday</key><integer>4</integer>
            <key>Hour</key><integer>18</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- Fredag -->
        <dict>
            <key>Weekday</key><integer>5</integer>
            <key>Hour</key><integer>18</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        
        <!-- ========== EOD utvärdering (23:00 CET) ========== -->
        <!-- Måndag -->
        <dict>
            <key>Weekday</key><integer>1</integer>
            <key>Hour</key><integer>23</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <!-- Tisdag -->
        <dict>
            <key>Weekday</key><integer>2</integer>
            <key>Hour</key><integer>23</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <!-- Onsdag -->
        <dict>
            <key>Weekday</key><integer>3</integer>
            <key>Hour</key><integer>23</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <!-- Torsdag -->
        <dict>
            <key>Weekday</key><integer>4</integer>
            <key>Hour</key><integer>23</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <!-- Fredag -->
        <dict>
            <key>Weekday</key><integer>5</integer>
            <key>Hour</key><integer>23</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>/tmp/trading-triggers.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/trading-triggers-error.log</string>
</dict>
</plist>
```

**Status:** Laddad och aktiv
- Kontrollera med: `launchctl list se.xandgo.trading-triggers`
- Förväntad output visar `LastExitStatus: 0`

**Loggar:**
- Standard output: `/tmp/trading-triggers.log`
- Fel: `/tmp/trading-triggers-error.log`

### 3. Kör-script: `run_daily.sh`
```bash
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# Bestäm evaluation_time baserat på aktuell timme
HOUR=$(date +%H)
if [[ "$HOUR" -ge 16 && "$HOUR" -lt 18 ]]; then
    export EVALUATION_TIME="1h"
elif [[ "$HOUR" -ge 18 && "$HOUR" -lt 22 ]]; then
    export EVALUATION_TIME="2h"
elif [[ "$HOUR" -ge 22 && "$HOUR" -lt 24 ]]; then
    export EVALUATION_TIME="EOD"
else
    export EVALUATION_TIME="1h"
fi

cd /Users/xandgo/.openclaw/workspace/projects/trading-triggers
source .venv/bin/activate
python src/trigger_system_v1.py >> /tmp/trading-triggers.log 2>&1
```

### 4. Wrapper-script: `run_with_webhook.sh`
```bash
#!/bin/bash
cd "$(dirname "$0")"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
source .venv/bin/activate
python src/trigger_system_v1.py
```

### 5. Test-script: `test_webhook.py`
Skickar ett testmeddelande till webhooken för att verifiera att den fungerar.

---

## 📊 Dagens resultat (2026-05-23 — första körning)

| Aktie | Trigger | Öppning | Pris | Förändring | Resultat |
|-------|---------|---------|------|-----------|----------|
| NVDA | Open_Above | $220.90 | $215.25 | -2.56% | ❌ miss |
| WMT | Open_Above | $121.24 | $120.26 | -0.81% | ❌ miss |
| TTWO | Premarket_Break | $243.74 | $227.56 | -6.64% | ✅ hit |
| WDAY | Gap_Defense | $128.74 | $128.11 | -0.49% | ❌ miss |
| ENPH | Momentum | $62.48 | $64.01 | +2.45% | ✅ hit |

**Sammanfattning:** 2/5 träffar (40%)

---

## 🔧 Kommandon

### Manuell körning
```bash
cd projects/trading-triggers
./run_with_webhook.sh
```

### Testa webhook
```bash
cd projects/trading-triggers
python test_webhook.py
```

### Kontrollera LaunchAgent-status
```bash
launchctl list se.xandgo.trading-triggers
```

### Ladda om LaunchAgent (efter ändringar)
```bash
launchctl unload ~/Library/LaunchAgents/se.xandgo.trading-triggers.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/se.xandgo.trading-triggers.plist
```

### Felsökning
Om LaunchAgent inte startar:
```bash
# Kontrollera plist-syntax
plutil -lint ~/Library/LaunchAgents/se.xandgo.trading-triggers.plist

# Visa senaste loggar
tail -f /tmp/trading-triggers-error.log

# Kör manuellt för att se fel
bash /Users/xandgo/.openclaw/workspace/projects/trading-triggers/run_daily.sh
```

---

## 📈 Nästa steg

### ✅ Färdigt — MCP Server

**Status:** Klar och testad (2026-05-23)

En MCP-server (Model Context Protocol) är nu implementerad och tillgänglig för Marvin och andra agenter.

**Tools (8 stycken):**
| Tool | Beskrivning |
|------|-------------|
| `get_todays_triggers` | Lista dagens aktiva triggers |
| `evaluate_trigger` | Utvärdera en trigger manuellt |
| `get_historical_accuracy` | Träffsäkerhet över tid |
| `get_market_summary` | Marknadsöversikt för alla aktier |
| `add_stock` | Lägg till ny aktie i bevakning |
| `remove_stock` | Ta bort aktie från bevakning |
| `get_trigger_stats` | Detaljerad statistik per trigger-typ |
| `export_to_obsidian` | Exportera rapport till Obsidian |

**Körning:**
```bash
cd projects/trading-triggers
source .venv/bin/activate
python src/mcp_server.py
```

**Test:**
```bash
python tests/mcp_test_client.py   # stdio-transport, alla 8 tools
python tests/test_mcp_server.py   # direktanrop (snabbare)
```

**Tekniska detaljer:**
- Stdio-transport (JSON-RPC 2.0)
- Kopplar till `data/triggers.db`
- Exporterar till `~/Vaults/valvet/Valvet/`
- Dokumentation: `docs/MCP_SERVER.md`

### Planerade utbyggnader (från ursprungligt design)

**MVP (vecka 1–2):**
- ✅ Data Collector (yfinance)
- ✅ SQLite-databas
- ✅ Grundläggande triggers
- ✅ Discord-rapporter
- ✅ 1h-utvärdering

**Kommande (vecka 3–4):**
- ✅ MCP-server med 8 tools
- ✅ 2h/EOD-utvärdering (idempotent, LaunchAgent-schemalagd)
- ✅ Historisk statistik
- Retry/circuit breaker

**Avancerat (vecka 5–6):**
- Backtesting
- Obsidian-export
- Docker-container
- Reservkällor

---

## 📝 Viktiga anteckningar

- Webhook-URL är **hemlig** — dela inte utanför Valvet
- All körning loggas till `/tmp/trading-triggers.log`
- Databasen (`data/triggers.db`) sparar historik över tid
- Systemet använder `yfinance` för data — beroende av Yahoo Finance:s tillgänglighet

---

*Senast uppdaterad: 2026-05-23*
*Av: Marvin 🤖*
