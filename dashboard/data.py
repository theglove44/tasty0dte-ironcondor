"""Data loading layer for the dashboard.

Reads CSV, log files, and cache files. All functions return plain dicts/lists
suitable for Jinja2 templates. CSV is cached by mtime to avoid re-reading on
every HTMX poll.
"""

import json
import os
import re
import signal
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
import pytz

# ---------------------------------------------------------------------------
# Paths (relative to project root)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "paper_trades.csv")
SPX_CACHE = os.path.join(BASE_DIR, ".spx_cache.json")
BOT_PID = os.path.join(BASE_DIR, "bot.pid")
CRON_LOG = os.path.join(BASE_DIR, "cron.log")
TRADE_LOG = os.path.join(BASE_DIR, "trade.log")
STDERR_LOG = os.path.join(BASE_DIR, "stderr.log")

UK = pytz.timezone("Europe/London")

# ---------------------------------------------------------------------------
# CSV cache
# ---------------------------------------------------------------------------
_csv_cache = {"mtime": 0, "df": None}


def load_trades() -> pd.DataFrame:
    """Load paper_trades.csv with mtime-based caching."""
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()

    mtime = os.path.getmtime(CSV_PATH)
    if mtime != _csv_cache["mtime"] or _csv_cache["df"] is None:
        df = pd.read_csv(CSV_PATH, dtype=str)
        df.columns = df.columns.str.strip()
        # Numeric conversions
        for col in ("Credit Collected", "Buying Power", "Profit Target", "Exit P/L", "IV Rank"):
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
                    errors="coerce",
                )
        _csv_cache["mtime"] = mtime
        _csv_cache["df"] = df
    return _csv_cache["df"]


# ---------------------------------------------------------------------------
# Strike parsing
# ---------------------------------------------------------------------------
_STRIKE_RE = re.compile(r"[CP](\d+)$")


def _parse_strike(symbol: str) -> str:
    if not isinstance(symbol, str):
        return "?"
    m = _STRIKE_RE.search(symbol.strip())
    return m.group(1) if m else "?"


# ---------------------------------------------------------------------------
# Public data functions
# ---------------------------------------------------------------------------

def get_open_positions() -> list[dict]:
    df = load_trades()
    if df.empty:
        return []
    mask = df["Status"].str.strip().str.upper() == "OPEN"
    rows = df[mask]
    result = []
    for _, r in rows.iterrows():
        result.append({
            "strategy": r.get("Strategy", ""),
            "strategy_id": r.get("StrategyId", ""),
            "entry_time": r.get("Entry Time", ""),
            "short_call": _parse_strike(r.get("Short Call", "")),
            "long_call": _parse_strike(r.get("Long Call", "")),
            "short_put": _parse_strike(r.get("Short Put", "")),
            "long_put": _parse_strike(r.get("Long Put", "")),
            "credit": r.get("Credit Collected"),
            "profit_target": r.get("Profit Target"),
            "iv_rank": r.get("IV Rank"),
            "date": r.get("Date", ""),
        })
    return result


def get_todays_closed_trades() -> dict:
    """Returns {'trades': [...], 'daily_pl': float}."""
    df = load_trades()
    today = datetime.now(UK).strftime("%Y-%m-%d")
    if df.empty:
        return {"trades": [], "daily_pl": 0.0}
    mask = (
        (df["Date"].str.strip() == today)
        & df["Status"].str.strip().str.upper().isin(["CLOSED", "EXPIRED"])
    )
    rows = df[mask]
    trades = []
    for _, r in rows.iterrows():
        trades.append({
            "strategy": r.get("Strategy", ""),
            "entry_time": r.get("Entry Time", ""),
            "exit_time": r.get("Exit Time", ""),
            "credit": r.get("Credit Collected"),
            "exit_pl": r.get("Exit P/L"),
            "notes": r.get("Notes", ""),
            "status": r.get("Status", "").strip().upper(),
        })
    daily_pl = rows["Exit P/L"].sum() if not rows.empty else 0.0
    return {"trades": trades, "daily_pl": round(daily_pl, 2)}


def get_performance_metrics(period: str = "all") -> dict:
    """Compute performance metrics for a given period.

    Returns dict with keys: overall, by_strategy, equity_curve, calendar.
    """
    df = load_trades()
    if df.empty:
        return _empty_perf()

    closed = df[df["Status"].str.strip().str.upper().isin(["CLOSED", "EXPIRED"])].copy()
    if closed.empty:
        return _empty_perf()

    # Parse dates for filtering
    closed["_date"] = pd.to_datetime(closed["Date"].str.strip(), format="%Y-%m-%d", errors="coerce")
    closed = closed.dropna(subset=["_date"])

    now = datetime.now(UK)
    today = now.date()
    if period == "day":
        closed = closed[closed["_date"].dt.date == today]
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        closed = closed[closed["_date"].dt.date >= start]
    elif period == "month":
        closed = closed[(closed["_date"].dt.year == today.year) & (closed["_date"].dt.month == today.month)]
    elif period == "year":
        closed = closed[closed["_date"].dt.year == today.year]
    # else: all

    if closed.empty:
        return _empty_perf()

    overall = _calc_metrics(closed)

    # Per-strategy breakdown
    by_strategy = []
    for strat, grp in closed.groupby("Strategy"):
        m = _calc_metrics(grp)
        m["strategy"] = strat.strip() if isinstance(strat, str) else str(strat)
        by_strategy.append(m)

    # Equity curve (cumulative P/L by date)
    daily = closed.groupby(closed["_date"].dt.date)["Exit P/L"].sum().sort_index()
    cum = daily.cumsum()
    equity_curve = {
        "labels": [d.strftime("%Y-%m-%d") for d in cum.index],
        "values": [round(v, 2) for v in cum.values],
    }

    # Calendar heatmap (daily P/L)
    calendar = {
        "labels": [d.strftime("%Y-%m-%d") for d in daily.index],
        "values": [round(v, 2) for v in daily.values],
    }

    return {
        "overall": overall,
        "by_strategy": by_strategy,
        "equity_curve": equity_curve,
        "calendar": calendar,
        "period": period,
    }


def _calc_metrics(df: pd.DataFrame) -> dict:
    total = len(df)
    pl = df["Exit P/L"].fillna(0)
    winners = pl[pl > 0]
    losers = pl[pl <= 0]
    win_count = len(winners)
    win_rate = (win_count / total * 100) if total else 0
    avg_credit = df["Credit Collected"].mean() if "Credit Collected" in df.columns else 0
    avg_pl = pl.mean()
    total_pl = pl.sum()
    avg_win = winners.mean() if len(winners) else 0
    avg_loss = losers.mean() if len(losers) else 0
    prob_win = win_count / total if total else 0
    prob_loss = 1 - prob_win
    expectancy = (prob_win * avg_win) + (prob_loss * avg_loss) if total else 0
    return {
        "total_trades": total,
        "win_rate": round(win_rate, 1),
        "total_pl": round(total_pl, 2),
        "avg_credit": round(avg_credit, 2) if pd.notna(avg_credit) else 0,
        "avg_pl": round(avg_pl, 2) if pd.notna(avg_pl) else 0,
        "avg_win": round(avg_win, 2) if pd.notna(avg_win) else 0,
        "avg_loss": round(avg_loss, 2) if pd.notna(avg_loss) else 0,
        "expectancy": round(expectancy, 2) if pd.notna(expectancy) else 0,
    }


def _empty_perf() -> dict:
    return {
        "overall": {
            "total_trades": 0, "win_rate": 0, "total_pl": 0,
            "avg_credit": 0, "avg_pl": 0, "avg_win": 0, "avg_loss": 0,
            "expectancy": 0,
        },
        "by_strategy": [],
        "equity_curve": {"labels": [], "values": []},
        "calendar": {"labels": [], "values": []},
        "period": "all",
    }


def get_spx_data() -> dict:
    """Return SPX price + staleness info from .spx_cache.json."""
    if not os.path.exists(SPX_CACHE):
        return {"price": None, "timestamp": None, "stale": True}
    try:
        with open(SPX_CACHE) as f:
            data = json.load(f)
        ts = data.get("timestamp", "")
        price = data.get("price")
        # Staleness: > 5 minutes old
        stale = True
        if ts:
            cache_dt = datetime.fromisoformat(ts)
            if cache_dt.tzinfo is None:
                cache_dt = UK.localize(cache_dt)
            age = datetime.now(UK) - cache_dt
            stale = age.total_seconds() > 300
        return {"price": price, "timestamp": ts, "stale": stale}
    except Exception:
        return {"price": None, "timestamp": None, "stale": True}


def get_market_session() -> dict:
    """Determine current market session status (UK timezone)."""
    now = datetime.now(UK)
    weekday = now.weekday()  # 0=Mon, 6=Sun

    if weekday >= 5:
        return {"status": "Closed", "detail": "Weekend", "countdown": ""}

    market_open = now.replace(hour=14, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=21, minute=0, second=0, microsecond=0)

    if now < market_open:
        delta = market_open - now
        return {
            "status": "Pre-Market",
            "detail": "Opens at 14:30 UK",
            "countdown": _format_delta(delta),
        }
    elif now <= market_close:
        delta = market_close - now
        return {
            "status": "Open",
            "detail": "Closes at 21:00 UK",
            "countdown": _format_delta(delta),
        }
    else:
        return {"status": "Closed", "detail": "After hours", "countdown": ""}


def _format_delta(td: timedelta) -> str:
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def get_bot_status() -> dict:
    """Check if the bot process is running via bot.pid."""
    if not os.path.exists(BOT_PID):
        return {"running": False, "pid": None}
    try:
        with open(BOT_PID) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # signal 0 = existence check
        return {"running": True, "pid": pid}
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return {"running": False, "pid": None}


def get_cron_entries(n: int = 20) -> list[dict]:
    """Parse last n entries from cron.log."""
    lines = _tail_file(CRON_LOG, n)
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Format: [Mon Feb 23 21:15:02 GMT 2026] Message
        m = re.match(r"\[(.+?)\]\s*(.*)", line)
        if m:
            entries.append({"timestamp": m.group(1), "message": m.group(2)})
        else:
            entries.append({"timestamp": "", "message": line})
    return entries


def get_recent_errors(n: int = 20) -> list[dict]:
    """Grep last n ERROR/WARNING lines from trade.log and stderr.log."""
    errors = []
    for logfile in (TRADE_LOG, STDERR_LOG):
        lines = _tail_file(logfile, 200)
        source = os.path.basename(logfile)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.search(r"\b(ERROR|WARNING|WARN|Traceback|Exception)\b", line, re.IGNORECASE):
                errors.append({"source": source, "line": line})
    # Return most recent n
    return errors[-n:]


def get_pdt_status() -> dict:
    """Count day trades in rolling 5 business days for PDT tracking."""
    df = load_trades()
    if df.empty:
        return {"count": 0, "limit": 3, "trades": []}

    closed = df[df["Status"].str.strip().str.upper().isin(["CLOSED", "EXPIRED"])].copy()
    if closed.empty:
        return {"count": 0, "limit": 3, "trades": []}

    closed["_date"] = pd.to_datetime(closed["Date"].str.strip(), format="%Y-%m-%d", errors="coerce")
    closed = closed.dropna(subset=["_date"])

    today = datetime.now(UK).date()
    # Rolling 5 business days
    bdays = pd.bdate_range(end=today, periods=5)
    start = bdays[0].date()

    recent = closed[closed["_date"].dt.date >= start]
    # Each closed 0DTE trade counts as a day trade
    day_trade_dates = recent.groupby(recent["_date"].dt.date).size()
    trades_list = [
        {"date": d.strftime("%Y-%m-%d"), "count": int(c)}
        for d, c in day_trade_dates.items()
    ]
    return {
        "count": len(recent),
        "limit": 3,
        "trades": trades_list,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tail_file(path: str, n: int = 50) -> list[str]:
    """Read last n lines from a file using seek-from-end for large files."""
    if not os.path.exists(path):
        return []
    try:
        size = os.path.getsize(path)
        if size == 0:
            return []
        # For files under 100KB, just read all
        if size < 100_000:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.readlines()[-n:]
        # For large files, seek from end
        with open(path, "rb") as f:
            buf_size = min(size, n * 500)  # ~500 bytes per line estimate
            f.seek(max(0, size - buf_size))
            tail = f.read().decode("utf-8", errors="replace")
            lines = tail.splitlines(keepends=True)
            # Drop partial first line
            if len(lines) > 1:
                lines = lines[1:]
            return lines[-n:]
    except Exception:
        return []
