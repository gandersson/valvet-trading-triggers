#!/usr/bin/env python3
"""
REST API + Swagger for Trading Trigger System.

Exposes the same capabilities as the CLI and MCP server
over a FastAPI HTTP API with automatic OpenAPI docs.

Start:  uvicorn api_server:app --reload
Swagger: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

# Ensure src/ is on the path so we can import sibling modules
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import trigger_system_v1 as ts

# ── Pydantic models ──────────────────────────────────────────────────────────


class TriggerCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    trigger_type: str = Field(default="Open_Above")
    condition: str = Field(default="price > open")
    source: str = Field(default="api")


class TriggerResponse(BaseModel):
    id: int
    date: str
    symbol: str
    trigger_type: str
    condition: str
    source: str | None
    status: str


class EvaluationResult(BaseModel):
    symbol: str
    trigger_type: str
    condition: str
    open: float
    price: float
    change_pct: float
    result: str
    volume: int
    evaluation_time: str


class SignalResponse(BaseModel):
    symbol: str
    signal: str
    direction: str
    strength: int
    confidence_score: float
    trigger_result: bool
    recommendation: str
    trigger_type: str | None = None
    n1: float | None = None
    n2: float | None = None
    historical: float | None = None


class HistoricalStat(BaseModel):
    symbol: str
    trigger_type: str
    total: int
    hits: int
    misses: int
    hit_rate: float


class MarketDataItem(BaseModel):
    id: int | None = None
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class EvaluateAllResponse(BaseModel):
    evaluation_time: str
    results: list[EvaluationResult]
    signals: list[SignalResponse]


class BacktestRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["NVDA", "WMT", "TTWO", "WDAY", "ENPH"])
    days: int = Field(default=30, ge=1, le=365)
    start_date: str | None = None
    end_date: str | None = None


class BacktestResultItem(BaseModel):
    symbol: str
    trigger_type: str
    condition: str
    target_date: str
    evaluation_time: str
    open_price: float
    price_at_eval: float
    change_pct: float
    result: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ensure_db() -> None:
    """Create DB and tables if they don't exist."""
    ts.init_db()
    try:
        import backtest as _bt
        import sector_analysis as _sa

        _bt.init_backtest_tables()
        _sa.init_sector_analysis_tables()
    except Exception:
        pass


def _rows_to_dicts(cursor, rows) -> list:
    """Convert sqlite row tuples into dicts using cursor.description."""
    if not rows:
        return []
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row, strict=False)) for row in rows]


# ── Startup ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_db()
    yield


app = FastAPI(
    title="Trading Trigger System API",
    description="Evaluate stock triggers, get signals, and backtest strategies.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    """Simple health check."""
    return {"status": "ok", "time": datetime.now().isoformat()}


# ── Triggers ─────────────────────────────────────────────────────────────────


@app.get("/triggers", response_model=list[TriggerResponse], tags=["Triggers"])
def list_triggers(date: str | None = Query(default=None, description="Date YYYY-MM-DD, defaults to today")):
    """List triggers for a given date. Defaults to today."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = ts.get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT id, date, symbol, trigger_type, condition, source, status "
            "FROM triggers WHERE date = ? AND status = 'active' ORDER BY symbol",
            (date,),
        )
        rows = c.fetchall()
        return [] if not rows else [TriggerResponse(**d) for d in _rows_to_dicts(c, rows)]
    finally:
        conn.close()


@app.post("/triggers", response_model=TriggerResponse, status_code=201, tags=["Triggers"])
def create_trigger(body: TriggerCreate):
    """Add a new trigger for today."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = ts.get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO triggers (date, symbol, trigger_type, condition, source, status) "
            "VALUES (?, ?, ?, ?, ?, 'active')",
            (today, body.symbol, body.trigger_type, body.condition, body.source),
        )
        conn.commit()
        trigger_id = c.lastrowid
        return TriggerResponse(
            id=trigger_id,
            date=today,
            symbol=body.symbol,
            trigger_type=body.trigger_type,
            condition=body.condition,
            source=body.source,
            status="active",
        )
    finally:
        conn.close()


@app.delete("/triggers/{symbol}", tags=["Triggers"])
def remove_trigger(symbol: str):
    """Deactivate today's triggers for a symbol."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = ts.get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "UPDATE triggers SET status = 'inactive' WHERE symbol = ? AND date = ?",
            (symbol, today),
        )
        conn.commit()
        return {"symbol": symbol, "status": "inactive", "date": today}
    finally:
        conn.close()


# ── Evaluation ───────────────────────────────────────────────────────────────


@app.post("/evaluate/all", response_model=EvaluateAllResponse, tags=["Evaluation"])
def evaluate_all(evaluation_time: str = Query(default="1h", pattern="^(1h|2h|EOD)$")):
    """Run the full evaluation pipeline: fetch data, evaluate triggers, generate signals."""
    results, signals = ts.evaluate_all_triggers(evaluation_time=evaluation_time)
    # Convert dicts to Pydantic models
    eval_results = [EvaluationResult(**r) for r in results]
    sig_results = []
    for s in signals or []:
        s_copy = dict(s)
        if "n1" not in s_copy:
            s_copy["n1"] = None
        if "n2" not in s_copy:
            s_copy["n2"] = None
        if "historical" not in s_copy:
            s_copy["historical"] = None
        sig_results.append(SignalResponse(**s_copy))
    return EvaluateAllResponse(
        evaluation_time=evaluation_time,
        results=eval_results,
        signals=sig_results,
    )


@app.post("/evaluate", response_model=EvaluationResult, tags=["Evaluation"])
def evaluate_single(
    symbol: str = Query(...),
    trigger_type: str = Query(default="Open_Above"),
    current_price: float | None = Query(default=None),
    open_price: float | None = Query(default=None),
):
    """Evaluate a single trigger manually, fetching live data if prices not provided."""
    if current_price is not None and open_price is not None:
        data = {
            "symbol": symbol,
            "price": current_price,
            "open": open_price,
            "change_pct": ((current_price - open_price) / open_price * 100),
            "high": current_price,
            "low": current_price,
            "volume": 0,
            "timestamp": datetime.now().isoformat(),
        }
    else:
        try:
            data = ts.fetch_stock_data(symbol)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch data: {e}") from e

    result = ts.evaluate_trigger(data, trigger_type)
    evaluation_time = datetime.now().strftime("%H")  # approximate

    if result not in ("hit", "miss"):
        raise HTTPException(status_code=400, detail=f"Unable to evaluate trigger; result was '{result}'")

    # Save evaluation and stats
    today = datetime.now().strftime("%Y-%m-%d")
    conn = ts.get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT id FROM triggers WHERE symbol = ? AND date = ? AND status = 'active' LIMIT 1", (symbol, today)
        )
        row = c.fetchone()
        if row:
            trigger_id = row[0]
            c.execute(
                "INSERT OR REPLACE INTO evaluations "
                "(trigger_id, evaluation_time, price_at_eval, open_price, result, evaluated_at) "
                "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (trigger_id, evaluation_time, data["price"], data["open"], result),
            )
            conn.commit()
        ts.update_trigger_stats(symbol, trigger_type, result, data["change_pct"])
    finally:
        conn.close()

    return EvaluationResult(
        symbol=symbol,
        trigger_type=trigger_type,
        condition="price > open",
        open=data["open"],
        price=data["price"],
        change_pct=data["change_pct"],
        result=result,
        volume=data["volume"],
        evaluation_time=evaluation_time,
    )


# ── Signals ──────────────────────────────────────────────────────────────────


@app.get("/signals", response_model=list[SignalResponse], tags=["Signals"])
def list_signals(
    date: str | None = Query(default=None, description="Date YYYY-MM-DD, defaults to today"),
):
    """Get generated signals, optionally filtered by date."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = ts.get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT date, evaluation_time, symbol, trigger_type, trigger_result, "
            "signal_type, direction, strength, confidence_score, recommendation "
            "FROM signals WHERE date = ? ORDER BY symbol, evaluation_time",
            (date,),
        )
        rows = c.fetchall()
        if not rows:
            return []
        result = []
        for d in _rows_to_dicts(c, rows):
            result.append(
                SignalResponse(
                    symbol=d["symbol"],
                    signal=d["signal_type"],
                    direction=d["direction"],
                    strength=d["strength"],
                    confidence_score=d["confidence_score"],
                    trigger_result=(d["trigger_result"] == "hit"),
                    recommendation=d["recommendation"],
                    trigger_type=d.get("trigger_type"),
                )
            )
        return result
    finally:
        conn.close()


# ── Historical stats ─────────────────────────────────────────────────────────


@app.get("/stats", response_model=list[HistoricalStat], tags=["Stats"])
def trigger_stats(symbol: str | None = Query(default=None)):
    """Get historical hit-rate stats per symbol/trigger_type."""
    stats = ts.get_historical_accuracy(symbol=symbol)
    return [HistoricalStat(**s) for s in stats]


@app.get("/stats/accuracy", tags=["Stats"])
def accuracy_detail(symbol: str = Query(...), trigger_type: str = Query(default="Open_Above")):
    """Get detailed accuracy breakdown (N1, N2, historical)."""
    n1 = ts.get_trigger_accuracy(symbol, trigger_type)
    try:
        n2 = ts.get_sector_correlation_accuracy(symbol)
    except Exception:
        n2 = 0.5
    historical = ts.get_historical_combined_accuracy(symbol)
    return {
        "symbol": symbol,
        "trigger_type": trigger_type,
        "n1_trigger_accuracy": n1,
        "n2_sector_accuracy": n2,
        "historical_combined_accuracy": historical,
    }


# ── Market data ──────────────────────────────────────────────────────────────


@app.get("/market-data", response_model=list[MarketDataItem], tags=["Market Data"])
def market_summary(symbol: str | None = Query(default=None)):
    """Get latest market data, optionally filtered by symbol."""
    conn = ts.get_db_connection()
    c = conn.cursor()
    try:
        if symbol:
            c.execute(
                "SELECT id, symbol, timestamp, open, high, low, close, volume "
                "FROM market_data WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
                (symbol,),
            )
        else:
            c.execute(
                "SELECT m.id, m.symbol, m.timestamp, m.open, m.high, m.low, m.close, m.volume "
                "FROM market_data m "
                "INNER JOIN (SELECT symbol, MAX(timestamp) as max_ts FROM market_data GROUP BY symbol) latest "
                "ON m.symbol = latest.symbol AND m.timestamp = latest.max_ts "
                "ORDER BY m.symbol",
            )
        rows = c.fetchall()
        return [MarketDataItem(**d) for d in _rows_to_dicts(c, rows)]
    finally:
        conn.close()


# ── Backtest ─────────────────────────────────────────────────────────────────


@app.post("/backtest", response_model=list[BacktestResultItem], tags=["Backtest"])
def run_backtest(body: BacktestRequest):
    """Run a backtest over historical data. Results are also saved to the database."""
    from datetime import date, timedelta

    import backtest as bt

    if body.start_date and body.end_date:
        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
    else:
        end = date.today()
        start = end - timedelta(days=body.days)

    bt.init_backtest_tables()
    results, _ = bt.run_backtest(body.symbols, start, end)
    return [BacktestResultItem(**r) for r in results]


# ── Obsidian export ──────────────────────────────────────────────────────────


@app.post("/obsidian/export", tags=["Export"])
def export_to_obsidian():
    """Export a daily markdown report to Obsidian vault."""
    from pathlib import Path

    vault = Path.home() / "Vaults" / "valvet" / "Valvet"
    vault.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    conn = ts.get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT t.symbol, t.trigger_type, t.condition, e.result, e.price_at_eval, e.open_price, e.evaluation_time "
            "FROM triggers t LEFT JOIN evaluations e ON t.id = e.trigger_id "
            "WHERE t.date = ? AND t.status = 'active' ORDER BY t.symbol",
            (today,),
        )
        fetched = c.fetchall()
        rows = _rows_to_dicts(c, fetched)
    finally:
        conn.close()

    lines = [f"# Trading Trigger Rapport – {today}\n"]
    for r in rows:
        emoji = "✅" if r.get("result") == "hit" else "❌"
        lines.append(
            f"| {emoji} {r['symbol']} | {r.get('trigger_type', '-')} | "
            f"${r.get('open_price', '?')} → ${r.get('price_at_eval', '?')} |"
        )

    filepath = vault / f"{today}.md"
    filepath.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "exported", "file": str(filepath)}
