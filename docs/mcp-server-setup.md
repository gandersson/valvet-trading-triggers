# MCP Server — Setup Guide

Guide för att köra Trading Triggers som standalone MCP-server i Claude Desktop eller Cursor.

---

## Förutsättningar

- Python 3.13+
- Git

---

## 1. Klona repo

```bash
git clone https://github.com/gandersson/valvet-trading-triggers.git
cd valvet-trading-triggers
```

---

## 2. Installera dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Viktigt:** `mcp`-paketet måste finnas installerat. Om `requirements.txt` saknar det:

```bash
pip install mcp
```

---

## 3. Konfigurera Claude Desktop

### macOS

Redigera `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trading-triggers": {
      "command": "/Users/xandgo/dev/trading-triggers/.venv/bin/python",
      "args": ["/Users/xandgo/dev/trading-triggers/src/mcp_server.py"]
    }
  }
}
```

**Notera:** Använd absoluta sökvägar. Byt ut `/Users/xandgo/dev/trading-triggers` mot din faktiska sökväg.

### Windows

Redigera `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trading-triggers": {
      "command": "C:\\Users\\<user>\\dev\\trading-triggers\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\<user>\\dev\\trading-triggers\\src\\mcp_server.py"]
    }
  }
}
```

---

## 4. Konfigurera Cursor

Redigera `~/.cursor/mcp.json` (macOS) eller motsvarande på Windows:

```json
{
  "mcpServers": {
    "trading-triggers": {
      "command": "/Users/xandgo/dev/trading-triggers/.venv/bin/python",
      "args": ["/Users/xandgo/dev/trading-triggers/src/mcp_server.py"]
    }
  }
}
```

---

## 5. Verifiera att servern startar

Testa manuellt innan du startar om Claude/Cursor:

```bash
python src/mcp_server.py
```

Om allt är OK händer inget synligt (servern väntar på stdio-anrop). Tryck `Ctrl+C` för att avbryta.

Om du får fel:
- Kontrollera att `.venv` är aktiverad och `mcp` är installerat
- Kontrollera att `data/triggers.db` finns (eller skapas vid första körning)
- Se till att `config/.env` finns om Discord-webhook behövs

---

## Tillgängliga tools

| Tool | Beskrivning |
|------|-------------|
| `get_todays_triggers` | Lista dagens aktiva triggers. Filter: `symbol` (valfritt) |
| `evaluate_trigger` | Utvärdera specifik trigger. Kräver: `symbol`, `trigger_type`. Valfritt: `current_price`, `open_price` |
| `get_historical_accuracy` | Träffsäkerhet över tid. Filter: `symbol`, `days` (default: 30) |
| `get_market_summary` | Senaste marknadsdata för alla aktier. Filter: `symbol` |
| `add_stock` | Lägg till aktie i bevakning. Kräver: `symbol`. Valfritt: `trigger_type`, `condition` |
| `remove_stock` | Ta bort aktie från bevakning. Kräver: `symbol` |
| `get_trigger_stats` | Detaljerad statistik per trigger-typ. Filter: `symbol` |
| `export_to_obsidian` | Exportera rapport till Obsidian. Valfritt: `report_type` (daily/weekly/monthly) |

---

## Exempelanvändning i Claude

**Fråga:** "Vilka triggers är aktiva idag?"

Claude anropar `get_todays_triggers` och visar resultatet.

**Fråga:** "Hur har NVDA presterat de senaste 30 dagarna?"

Claude anropar `get_historical_accuracy` med `symbol: "NVDA"`, `days: 30`.

**Fråga:** "Utvärdera WMT:s Open Above-trigger."

Claude anropar `evaluate_trigger` med `symbol: "WMT"`, `trigger_type: "Open_Above"`.

---

## Felsökning

### Servern syns inte i Claude/Cursor

1. Starta om appen efter config-ändringar
2. Kontrollera att JSON-syntaxen är korrekt (kommatecken, brackets)
3. Se loggar i Claude Desktop: `Help → Toggle Developer Tools → Console`

### `ModuleNotFoundError: mcp`

```bash
pip install mcp
# eller
pip install -r requirements.txt
```

### Databas-fel

Om `triggers.db` saknas eller är korrupt:

```bash
python src/trigger_system_v1.py  # Skapar databasen vid första körning
```

---

*Senast uppdaterad: 2026-05-25*
