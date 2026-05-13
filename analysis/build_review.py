#!/usr/bin/env python3
"""
build_review.py
===============
Generate a standalone strategy review HTML page from paper_trades.csv.

Usage:
    python3 analysis/build_review.py
    python3 analysis/build_review.py --out /path/to/review.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# Trades with known PT-miss (stale pricing): closed far past 10% target.
# Flagged 2026-05-12 after comparing Exit P/L vs expected 10% of credit.
PT_MISS_DATES = {"2026-04-20", "2026-04-02", "2026-03-24", "2026-03-31"}

ACTIVE = {"Iron Fly V1", "Iron Fly V2", "Iron Fly V3", "Iron Fly V4", "Dynamic 0DTE"}
REMOVED = {"20 Delta", "30 Delta", "Gap Filter 20D"}

STRATEGY_ORDER_DISPLAY = [
    "Iron Fly V1", "Iron Fly V2", "Iron Fly V3", "Iron Fly V4",
    "Dynamic 0DTE", "ORB-STACK-DOUBLE",
    "20 Delta", "30 Delta", "Gap Filter 20D",
]


def hold_minutes(row) -> int | None:
    et = row.get("Exit Time", "")
    if pd.isna(et) or str(et).strip() in ("", "nan"):
        return None
    try:
        eh, em, _ = row["Entry Time"].split(":")
        xh, xm, _ = str(et).split(":")
        v = (int(xh) * 60 + int(xm)) - (int(eh) * 60 + int(em))
        return v if v >= 0 else None
    except Exception:
        return None


def compute_metrics(grp: pd.DataFrame) -> dict:
    grp = grp.sort_values(["Date", "Entry Time"]).reset_index(drop=True)
    pl = grp["Exit P/L"].values.astype(float)
    n = len(pl)
    if n == 0:
        return {}

    wins_arr = pl[pl > 0]
    losses_arr = pl[pl <= 0]
    win_n = len(wins_arr)
    loss_n = len(losses_arr)

    wstreaks, lstreaks = common.streaks(pl)

    cum = np.cumsum(pl)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = float(dd.min()) if len(dd) else 0

    # Drawdown recovery
    if max_dd < 0:
        i_low = int(np.argmin(dd))
        i_peak = int(np.argmax(cum[: i_low + 1])) if i_low > 0 else 0
        pv = peak[i_low]
        i_rec = next((i for i in range(i_low + 1, len(cum)) if cum[i] >= pv), None)
        dd_to_bot = i_low - i_peak
        dd_to_rec = (i_rec - i_low) if i_rec is not None else None
    else:
        dd_to_bot, dd_to_rec = 0, 0

    gp = float(wins_arr.sum()) if win_n else 0
    gl = float(abs(losses_arr.sum())) if loss_n else 0
    pf = round(gp / gl, 2) if gl > 0 else None

    holds = [h for _, r in grp.iterrows() if (h := hold_minutes(r)) is not None]

    std = float(pl.std(ddof=1)) if n > 1 else 0
    sharpe = round(float(pl.mean() / std), 2) if std > 0 else 0

    # Count PT-miss trades
    pt_miss = int(grp["Date"].astype(str).isin(PT_MISS_DATES).sum())

    # Exit type split
    def _exit_type(r):
        notes = str(r["Notes"]) if pd.notna(r["Notes"]) else ""
        if r["Status"] == "EXPIRED":
            return "expired"
        if "Time Exit" in notes:
            return "time_exit"
        return "pt_close"

    grp["_et"] = grp.apply(_exit_type, axis=1)
    exit_counts = grp["_et"].value_counts().to_dict()

    return {
        "n": n,
        "total_pl": round(float(pl.sum()), 2),
        "avg_pl": round(float(pl.mean()), 2),
        "win_n": win_n,
        "loss_n": loss_n,
        "win_pct": round(win_n / n * 100, 1),
        "avg_win": round(float(wins_arr.mean()), 2) if win_n else 0,
        "avg_loss": round(float(losses_arr.mean()), 2) if loss_n else 0,
        "profit_factor": pf,
        "best": round(float(pl.max()), 2),
        "worst": round(float(pl.min()), 2),
        "max_dd": round(max_dd, 2),
        "dd_to_bot": dd_to_bot,
        "dd_to_rec": dd_to_rec,
        "max_win_streak": max(wstreaks) if wstreaks else 0,
        "max_loss_streak": max(lstreaks) if lstreaks else 0,
        "avg_win_streak": round(float(np.mean(wstreaks)), 1) if wstreaks else 0,
        "avg_loss_streak": round(float(np.mean(lstreaks)), 1) if lstreaks else 0,
        "num_win_streaks": len(wstreaks),
        "num_loss_streaks": len(lstreaks),
        "avg_hold": round(float(np.mean(holds)), 0) if holds else None,
        "median_hold": round(float(np.median(holds)), 0) if holds else None,
        "sharpe": sharpe,
        "pt_miss_trades": pt_miss,
        "exit_pt_close": exit_counts.get("pt_close", 0),
        "exit_time_exit": exit_counts.get("time_exit", 0),
        "exit_expired": exit_counts.get("expired", 0),
        "first_date": str(grp["Date"].min()),
        "last_date": str(grp["Date"].max()),
        "avg_credit": round(float(grp["Credit Collected"].mean()), 2),
        "equity_curve": [round(float(v), 2) for v in cum.tolist()],
    }


def render_html(all_metrics: dict) -> str:
    # Sort strategies by total P/L descending for ranking
    ranked = sorted(
        [(s, m) for s, m in all_metrics.items() if m],
        key=lambda x: x[1]["total_pl"],
        reverse=True,
    )

    # Build equity curve data (per strategy, indexed by trade number)
    eq_data = {s: m["equity_curve"] for s, m in all_metrics.items() if m}

    def badge(s):
        if s in ACTIVE:
            return '<span class="badge active">Active</span>'
        if s in REMOVED:
            return '<span class="badge removed">Removed</span>'
        return '<span class="badge other">Limited Data</span>'

    def pl_class(v):
        if v is None:
            return ""
        return "pos" if v > 0 else ("neg" if v < 0 else "")

    def fmt_pl(v, show_sign=True):
        if v is None:
            return "—"
        sign = "+" if v > 0 else ""
        return f"{sign}${v:.2f}"

    def fmt_pct(v):
        return f"{v:.1f}%" if v is not None else "—"

    def fmt_min(v):
        if v is None:
            return "—"
        h, m = int(v) // 60, int(v) % 60
        return f"{h}h {m:02d}m" if h else f"{m}m"

    def asterisk(m):
        return ' <span class="ast" title="Contains trades where PT fired far past target due to stale pricing (Apr 2, Mar 24, Mar 31, Apr 20)">*</span>' if m.get("pt_miss_trades", 0) > 0 else ""

    # Summary table rows
    summary_rows = ""
    for rank, (s, m) in enumerate(ranked, 1):
        row_class = "removed-row" if s in REMOVED else ""
        summary_rows += f"""
        <tr class="{row_class}">
          <td class="rank">#{rank}</td>
          <td class="strat-name">{s}{asterisk(m)} {badge(s)}</td>
          <td class="{pl_class(m['total_pl'])} mono">{fmt_pl(m['total_pl'])}</td>
          <td class="{pl_class(m['avg_pl'])} mono">{fmt_pl(m['avg_pl'])}</td>
          <td class="mono">{fmt_pct(m['win_pct'])}</td>
          <td class="{pl_class(-abs(m['max_dd'])) if m['max_dd'] < 0 else ''} mono">{fmt_pl(m['max_dd'], show_sign=False)}</td>
          <td class="mono">{m['max_win_streak']}</td>
          <td class="mono">{m['max_loss_streak']}</td>
          <td class="mono">{fmt_min(m['avg_hold'])}</td>
          <td class="mono">{m['profit_factor'] if m['profit_factor'] else '—'}</td>
          <td class="mono">{m['sharpe']}</td>
          <td class="mono">{m['n']}</td>
        </tr>"""

    # Per-strategy detail cards
    detail_cards = ""
    for s in STRATEGY_ORDER_DISPLAY:
        m = all_metrics.get(s)
        if not m:
            continue

        dd_rec_str = f"{m['dd_to_rec']} trades" if m['dd_to_rec'] is not None else "Not yet recovered"
        exit_breakdown = (
            f"PT close: {m['exit_pt_close']} &nbsp;|&nbsp; "
            f"Time exit: {m['exit_time_exit']} &nbsp;|&nbsp; "
            f"Expired: {m['exit_expired']}"
        )
        pt_warn = ""
        if m.get("pt_miss_trades", 0) > 0:
            pt_warn = f"""<div class="pt-warn">⚠ {m['pt_miss_trades']} trade(s) closed far past 10% PT — stale REST pricing suspected on high-volatility days (Apr 2, Mar 24, Mar 31, Apr 20). P/L is real but PT mechanism didn't fire at target.</div>"""

        detail_cards += f"""
    <div class="card {'removed-card' if s in REMOVED else ''}">
      <div class="card-header">
        <h2>{s}{asterisk(m)}</h2>
        {badge(s)}
        <span class="date-range">{m['first_date']} → {m['last_date']} &nbsp;({m['n']} trades)</span>
      </div>
      {pt_warn}
      <div class="metrics-grid">
        <div class="metric-group">
          <h3>P/L</h3>
          <div class="metric"><span>Total</span><span class="{pl_class(m['total_pl'])} mono">{fmt_pl(m['total_pl'])}</span></div>
          <div class="metric"><span>Avg/trade</span><span class="{pl_class(m['avg_pl'])} mono">{fmt_pl(m['avg_pl'])}</span></div>
          <div class="metric"><span>Best trade</span><span class="pos mono">{fmt_pl(m['best'])}</span></div>
          <div class="metric"><span>Worst trade</span><span class="neg mono">{fmt_pl(m['worst'])}</span></div>
          <div class="metric"><span>Avg credit</span><span class="mono">${m['avg_credit']:.2f}</span></div>
          <div class="metric"><span>Profit factor</span><span class="mono">{m['profit_factor'] if m['profit_factor'] else '—'}</span></div>
          <div class="metric"><span>Sharpe</span><span class="mono">{m['sharpe']}</span></div>
        </div>
        <div class="metric-group">
          <h3>Win / Loss</h3>
          <div class="metric"><span>Win rate</span><span class="mono">{fmt_pct(m['win_pct'])}</span></div>
          <div class="metric"><span>Wins / Losses</span><span class="mono">{m['win_n']}W / {m['loss_n']}L</span></div>
          <div class="metric"><span>Avg winner</span><span class="pos mono">{fmt_pl(m['avg_win'])}</span></div>
          <div class="metric"><span>Avg loser</span><span class="neg mono">{fmt_pl(m['avg_loss'])}</span></div>
          <div class="metric"><span>W:L ratio</span><span class="mono">{round(m['avg_win']/abs(m['avg_loss']),2) if m['avg_loss'] != 0 else '—'}</span></div>
        </div>
        <div class="metric-group">
          <h3>Drawdown</h3>
          <div class="metric"><span>Max DD</span><span class="neg mono">{fmt_pl(m['max_dd'])}</span></div>
          <div class="metric"><span>Trades to bottom</span><span class="mono">{m['dd_to_bot']}</span></div>
          <div class="metric"><span>Trades to recover</span><span class="mono">{dd_rec_str}</span></div>
        </div>
        <div class="metric-group">
          <h3>Streaks</h3>
          <div class="metric"><span>Max win streak</span><span class="pos mono">{m['max_win_streak']}</span></div>
          <div class="metric"><span>Avg win streak</span><span class="mono">{m['avg_win_streak']}</span></div>
          <div class="metric"><span>Max loss streak</span><span class="neg mono">{m['max_loss_streak']}</span></div>
          <div class="metric"><span>Avg loss streak</span><span class="mono">{m['avg_loss_streak']}</span></div>
        </div>
        <div class="metric-group">
          <h3>Hold Time</h3>
          <div class="metric"><span>Avg</span><span class="mono">{fmt_min(m['avg_hold'])}</span></div>
          <div class="metric"><span>Median</span><span class="mono">{fmt_min(m['median_hold'])}</span></div>
        </div>
        <div class="metric-group">
          <h3>Exit Breakdown</h3>
          <div class="metric-full">{exit_breakdown}</div>
        </div>
      </div>
      <div class="equity-chart" id="chart-{s.replace(' ','_').replace('/','_').replace('-','_')}"></div>
    </div>"""

    eq_json = json.dumps(eq_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Strategy Review — 0DTE SPX Bot</title>
<style>
  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #21262d;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #7d8590;
    --pos: #3fb950;
    --neg: #f85149;
    --warn: #d29922;
    --active: #388bfd;
    --removed: #6e7681;
    --other: #bc8cff;
    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.6; }}
  a {{ color: var(--active); }}

  .header {{ padding: 32px 40px 16px; border-bottom: 1px solid var(--border); }}
  .header h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 4px; }}
  .header .subtitle {{ color: var(--muted); font-size: 13px; }}

  .note-bar {{ background: #21262d; border-left: 3px solid var(--warn); color: #c9d1d9; padding: 10px 40px; font-size: 12.5px; }}

  .section {{ padding: 32px 40px; }}
  .section h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--text); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: var(--surface2); color: var(--muted); font-weight: 500; text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:hover td {{ background: var(--surface); }}
  tr.removed-row td {{ opacity: 0.6; }}
  .rank {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
  .strat-name {{ font-weight: 500; }}
  .mono {{ font-family: var(--mono); font-size: 12.5px; }}
  .pos {{ color: var(--pos); }}
  .neg {{ color: var(--neg); }}

  .badge {{ display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 500; margin-left: 6px; vertical-align: middle; }}
  .badge.active {{ background: rgba(56,139,253,0.15); color: var(--active); border: 1px solid rgba(56,139,253,0.3); }}
  .badge.removed {{ background: rgba(110,118,129,0.15); color: var(--removed); border: 1px solid rgba(110,118,129,0.3); }}
  .badge.other {{ background: rgba(188,140,255,0.15); color: var(--other); border: 1px solid rgba(188,140,255,0.3); }}
  .ast {{ color: var(--warn); cursor: help; font-size: 13px; }}

  .cards {{ display: flex; flex-direction: column; gap: 24px; padding: 0 40px 40px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
  .card.removed-card {{ opacity: 0.75; }}
  .card-header {{ display: flex; align-items: center; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }}
  .card-header h2 {{ font-size: 15px; font-weight: 600; }}
  .date-range {{ margin-left: auto; color: var(--muted); font-size: 12px; }}

  .pt-warn {{ background: rgba(210,153,34,0.1); border-left: 3px solid var(--warn); padding: 8px 16px; font-size: 12.5px; color: #d29922; margin: 0; }}

  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0; }}
  .metric-group {{ padding: 16px 20px; border-right: 1px solid var(--border); }}
  .metric-group:last-child {{ border-right: none; }}
  .metric-group h3 {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 10px; }}
  .metric {{ display: flex; justify-content: space-between; align-items: center; padding: 3px 0; font-size: 13px; gap: 8px; }}
  .metric span:first-child {{ color: var(--muted); white-space: nowrap; }}
  .metric-full {{ color: var(--muted); font-size: 12.5px; font-family: var(--mono); }}

  .equity-chart {{ padding: 0 20px 16px; }}
  .equity-chart canvas {{ width: 100%; height: 80px; display: block; }}

  .rankings {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
  .rank-list {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
  .rank-list h3 {{ font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 12px; }}
  .rank-item {{ display: flex; align-items: center; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid var(--border); font-size: 13px; }}
  .rank-item:last-child {{ border-bottom: none; }}
  .rank-item .ri-name {{ display: flex; align-items: center; gap: 6px; }}
  .rank-num {{ font-size: 11px; color: var(--muted); width: 20px; }}

  @media (max-width: 768px) {{
    .section, .cards {{ padding: 16px; }}
    .header {{ padding: 20px 16px 12px; }}
    .metrics-grid {{ grid-template-columns: 1fr 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>Strategy Review — 0DTE SPX Bot</h1>
  <div class="subtitle">Generated 2026-05-12 &nbsp;·&nbsp; 653 trades &nbsp;·&nbsp; Outlier filter: Credit &gt; $30 excluded &nbsp;·&nbsp; Private strategies excluded</div>
</div>

<div class="note-bar">
  * These strategies contain trades where the 10% profit target fired far past its threshold — stale REST pricing is the likely cause on volatile days (Apr 2, Mar 24, Mar 31, Apr 20). P/L is real and correctly logged; the PT mechanism just didn't catch the exit at the right moment.
</div>

<div class="section">
  <h2>Summary — Best to Worst by Total P/L</h2>
  <table>
    <thead>
      <tr>
        <th>Rank</th><th>Strategy</th><th>Total P/L</th><th>Avg/Trade</th>
        <th>Win Rate</th><th>Max DD</th><th>Max Win Streak</th>
        <th>Max Loss Streak</th><th>Avg Hold</th><th>Profit Factor</th>
        <th>Sharpe</th><th>Trades</th>
      </tr>
    </thead>
    <tbody>
      {summary_rows}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Rankings by Metric</h2>
  <div class="rankings">
    <div class="rank-list">
      <h3>Total P/L</h3>
      {''.join(f"""<div class="rank-item"><span class="ri-name"><span class="rank-num">#{i+1}</span>{s}</span><span class="{pl_class(m['total_pl'])} mono">{fmt_pl(m['total_pl'])}</span></div>""" for i,(s,m) in enumerate(ranked))}
    </div>
    <div class="rank-list">
      <h3>Win Rate</h3>
      {''.join(f"""<div class="rank-item"><span class="ri-name"><span class="rank-num">#{i+1}</span>{s}</span><span class="mono">{fmt_pct(m['win_pct'])}</span></div>""" for i,(s,m) in enumerate(sorted(all_metrics.items(), key=lambda x: x[1].get('win_pct',0), reverse=True) if all_metrics else []))}
    </div>
    <div class="rank-list">
      <h3>Max Drawdown (smallest)</h3>
      {''.join(f"""<div class="rank-item"><span class="ri-name"><span class="rank-num">#{i+1}</span>{s}</span><span class="{'neg' if m['max_dd']<0 else ''} mono">{fmt_pl(m['max_dd'])}</span></div>""" for i,(s,m) in enumerate(sorted(all_metrics.items(), key=lambda x: x[1].get('max_dd',0), reverse=True) if all_metrics else []))}
    </div>
    <div class="rank-list">
      <h3>Max Win Streak</h3>
      {''.join(f"""<div class="rank-item"><span class="ri-name"><span class="rank-num">#{i+1}</span>{s}</span><span class="pos mono">{m['max_win_streak']}</span></div>""" for i,(s,m) in enumerate(sorted(all_metrics.items(), key=lambda x: x[1].get('max_win_streak',0), reverse=True) if all_metrics else []))}
    </div>
    <div class="rank-list">
      <h3>Max Loss Streak (fewest)</h3>
      {''.join(f"""<div class="rank-item"><span class="ri-name"><span class="rank-num">#{i+1}</span>{s}</span><span class="{'neg' if m['max_loss_streak']>1 else ''} mono">{m['max_loss_streak']}</span></div>""" for i,(s,m) in enumerate(sorted(all_metrics.items(), key=lambda x: x[1].get('max_loss_streak',0)) if all_metrics else []))}
    </div>
    <div class="rank-list">
      <h3>Avg Hold Time (shortest)</h3>
      {''.join(f"""<div class="rank-item"><span class="ri-name"><span class="rank-num">#{i+1}</span>{s}</span><span class="mono">{fmt_min(m['avg_hold'])}</span></div>""" for i,(s,m) in enumerate(sorted([(s,m) for s,m in all_metrics.items() if m.get('avg_hold') is not None], key=lambda x: x[1]['avg_hold']) if all_metrics else []))}
    </div>
  </div>
</div>

<h2 style="padding: 8px 40px 0; font-size: 16px; font-weight: 600;">Strategy Detail Cards</h2>
<div class="cards">
  {detail_cards}
</div>

<script>
const EQ = {eq_json};

function drawChart(canvasId, data, color) {{
  const canvas = document.getElementById(canvasId);
  if (!canvas || !data || data.length < 2) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth;
  const H = canvas.offsetHeight;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);

  const min = Math.min(0, ...data);
  const max = Math.max(0, ...data);
  const range = max - min || 1;
  const pad = 8;

  const x = (i) => pad + (i / (data.length - 1)) * (W - pad * 2);
  const y = (v) => H - pad - ((v - min) / range) * (H - pad * 2);

  // Zero line
  ctx.strokeStyle = 'rgba(110,118,129,0.3)';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(0, y(0));
  ctx.lineTo(W, y(0));
  ctx.stroke();
  ctx.setLineDash([]);

  // Fill
  ctx.beginPath();
  ctx.moveTo(x(0), y(data[0]));
  data.forEach((v, i) => ctx.lineTo(x(i), y(v)));
  ctx.lineTo(x(data.length - 1), H - pad);
  ctx.lineTo(x(0), H - pad);
  ctx.closePath();
  ctx.fillStyle = color + '22';
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.moveTo(x(0), y(data[0]));
  data.forEach((v, i) => ctx.lineTo(x(i), y(v)));
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}}

const COLORS = {{
  'Iron Fly V1': '#3fb950',
  'Iron Fly V2': '#58a6ff',
  'Iron Fly V3': '#bc8cff',
  'Iron Fly V4': '#ffa657',
  'Dynamic 0DTE': '#39d353',
  'ORB-STACK-DOUBLE': '#79c0ff',
  '20 Delta': '#f85149',
  '30 Delta': '#ff7b72',
  'Gap Filter 20D': '#d29922',
}};

window.addEventListener('load', () => {{
  Object.entries(EQ).forEach(([name, data]) => {{
    const id = 'chart-' + name.replace(/[ /]/g, '_').replace(/-/g, '_');
    const canvas = document.getElementById(id);
    if (!canvas) return;
    canvas.width = canvas.parentElement.offsetWidth - 40;
    canvas.height = 80;
    drawChart(id, data, COLORS[name] || '#58a6ff');
  }});
}});
</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(common.CSV_PATH))
    ap.add_argument("--out", default=str(common.PROJECT_ROOT / "public_site" / "review.html"))
    args = ap.parse_args()

    df = common.load_trades(args.csv)

    all_metrics = {}
    for s, grp in df.groupby("Strategy"):
        all_metrics[s] = compute_metrics(grp)

    html = render_html(all_metrics)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size:,} bytes)")
    print(f"  Strategies: {len(all_metrics)}")
    for s, m in sorted(all_metrics.items(), key=lambda x: x[1].get("total_pl", 0), reverse=True):
        if m:
            print(f"    {s}: {m['n']} trades, total={fmt_pl(m['total_pl'])}, WR={fmt_pct(m['win_pct'])}")


def fmt_pl(v):
    if v is None:
        return "—"
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"

def fmt_pct(v):
    return f"{v:.1f}%" if v is not None else "—"


if __name__ == "__main__":
    main()
