# AGENTS.md — valvet-trading-triggers

## Git workflow

Use **feature branches** for all changes. Create a new branch, do the work there, then merge to `main` when done. Never commit directly to `main`.

```bash
# On main, create a tracked worktree for the feature
git worktree add -b feat/example-name ../valvet-trading-triggers-example main
cd ../valvet-trading-triggers-example
# ... do work, commit, push ...
# Go back to main worktree and merge when ready
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env  # then fill in DISCORD_WEBHOOK_URL
```

**No package install** — tests use `sys.path.insert(0, ...)` to reach `src/`.

## Commands

```bash
# Run (evaluation_time from $EVALUATION_TIME env, or first CLI arg: 1h, 2h, EOD)
python src/trigger_system_v1.py
python src/trigger_system_v1.py 1h

# Backtest
python src/backtest.py --days 30 --symbols NVDA,WMT

# Run all tests (MCP test requires `mcp` SDK not in requirements.txt — skip it)
python3 -m pytest tests/ --ignore=tests/test_mcp_server.py -v

# MCP server (requires mcp SDK installed separately)
python src/mcp_server.py

# REST API + Swagger
uvicorn api_server:app --reload --app-dir src       # dev mode, http://127.0.0.1:8000/docs

# Chat UI
# Starta API:et ovan, öppna sedan http://127.0.0.1:8000/chat
# Interaktivt chattgränssnitt med stöd för svenska kommandon:
#   utvärdera 1h | triggers | signaler | statistik NVDA | marknad WMT | backtest | hjälp

# Docker
docker build -t trading-triggers .
docker run -p 8000:8000 -v $(pwd)/data:/app/data trading-triggers
# Öppna http://localhost:8000/chat för chattgränssnittet
```

## Architecture

- `src/trigger_system_v1.py` — **monolith** (~740 lines): DB init, triggers, data fetch, evaluation, Discord reporting, signal generation. Main entrypoint.
- `src/signal_generator.py` — pure stateless signal logic (confidence scores, strength mapping). Used by `trigger_system_v1.py`.
- `src/data_fetcher.py` — Yahoo Finance first, with `YAHOO_TICKER_MAP` for exchange suffixes (e.g. `OVH → OVH.PA`). Has Avanza scraping fallback (empty by default).
- `src/resilience.py` — retry decorator (`@retry_yfinance`, 3 attempts, exponential backoff) + global `discord_circuit_breaker` singleton.
- `src/mcp_server.py` — MCP stdio server; imports `mcp` SDK (not pinned in requirements.txt).
- `src/api_server.py` — FastAPI REST API + Swagger (`/docs`). Wraps all trigger evaluation, signals, stats, market data, backtest, and Obsidian export.
- `src/static/chat.html` — single-page chattgränssnitt serverat på `/chat`. Vanilla HTML/CSS/JS, anropar REST-endpoints.

## Key gotchas

- **Relative DB path**: `DB_PATH = "data/triggers.db"` in `trigger_system_v1.py` is relative to CWD. Run from repo root. Tests that call functions using `get_db_connection()` need `data/` directory to exist.
- **5 tests fail** in `test_trigger_system_signals.py` when `data/` doesn't exist at CWD — they hit the real DB path.
- **Discord webhook URLs are hardcoded** in `run_daily.sh` and `run_with_webhook.sh`. Never commit changes to these.
- **No lint/formatter/typecheck config** — no `pyproject.toml`, no `ruff.toml`, no mypy config.
- **CI removed** — `.github/workflows/ci.yml` was deleted. No CI runs on push/PR.
- **`.env` lookup order**: `config/.env` → `~/.config/trading-triggers/.env` → `.env`. First found wins.

## Environment variables

| Variable | Values |
|---|---|
| `EVALUATION_TIME` | `1h`, `2h`, `EOD` |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL |

## Test quirks

- Tests that import from `trigger_system_v1` may create `data/` and `data/triggers.db` on disk — these are gitignored but can leave state.
- `test_mcp_server.py` fails to collect (missing `mcp` module). Skip with `--ignore=tests/test_mcp_server.py`.
- Tests use `unittest`-style classes but run with `pytest`.
