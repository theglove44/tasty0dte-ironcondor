"""
strategy_dashboard.py — Self-contained HTML performance dashboard for ONE strategy.

Renders a single offline HTML file (inline CSS + inline SVG charts + a tiny bit
of vanilla JS for tab/sort/filter, no server, no CDN) with:
  • Overview tab — KPIs, equity curve, drawdown, monthly/DOW, exit decomposition,
    hold-time outcomes, P/L histogram, detail + best/worst tables.
  • Trades tab — full chronological ledger, every trade + its individual metrics,
    sortable by any column and filterable by win/loss/exit-reason.

All stats/filters come from analysis/common.py (no re-implemented logic).

Usage:
  python analysis/strategy_dashboard.py "Iron Fly V1"
  python analysis/strategy_dashboard.py "Iron Fly V1" --out /tmp/v1.html --open
"""

from __future__ import annotations

import argparse
import calendar
import html as _html
import re
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# ---- palette (dark) ----------------------------------------------------------
BG, PANEL, INK, MUTED = "#0f1419", "#161b22", "#e6edf3", "#8b949e"
GREEN, RED, BLUE, AMBER, GRID = "#3fb950", "#f85149", "#58a6ff", "#d29922", "#30363d"

DOW_IDX = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4, "Friday": 5}


def money(v: float, dp: int = 2) -> str:
    return f"-${abs(v):,.{dp}f}" if v < 0 else f"${v:,.{dp}f}"


def esc(s) -> str:
    return _html.escape(str(s))


def parse_strike(s):
    m = re.search(r"[CP](\d+(?:\.\d+)?)$", str(s))
    return float(m.group(1)) if m else None


def ivr_display(v):
    """Best-effort normalise the inconsistently-scaled IV Rank to a 0-100 pct."""
    if v is None or pd.isna(v):
        return None
    return v * 100 if v <= 1.5 else float(v)


def mins_of(t):
    try:
        h, m, *_ = str(t).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return ""


# ---- tiny SVG chart helpers --------------------------------------------------

def _axis(W, H, pad):
    return (f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="{GRID}" stroke-width="1"/>')


def area_chart(values, W=720, H=300, pad=44, color=BLUE, fill_op=0.16, zero_base=True):
    n = len(values)
    if n < 2:
        return "<p style='color:#8b949e'>not enough data</p>"
    vmax = max(values + ([0] if zero_base else []))
    vmin = min(values + ([0] if zero_base else []))
    span = (vmax - vmin) or 1.0
    X = lambda i: pad + i / (n - 1) * (W - 2 * pad)
    Y = lambda v: pad + (vmax - v) / span * (H - 2 * pad)
    zeroY = Y(0)
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(values))
    area = f"{X(0):.1f},{zeroY:.1f} " + pts + f" {X(n-1):.1f},{zeroY:.1f}"
    grid = ""
    for gv in sorted({vmax, 0, vmin}):
        gy = Y(gv)
        grid += (f'<line x1="{pad}" y1="{gy:.1f}" x2="{W-pad}" y2="{gy:.1f}" stroke="{GRID}" '
                 f'stroke-dasharray="3 3" stroke-width="1"/>'
                 f'<text x="{pad-6:.0f}" y="{gy+3:.0f}" text-anchor="end" font-size="11" fill="{MUTED}">{money(gv,0)}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet">'
            f'{grid}<polygon points="{area}" fill="{color}" fill-opacity="{fill_op}"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>'
            f'<line x1="{pad}" y1="{zeroY:.1f}" x2="{W-pad}" y2="{zeroY:.1f}" stroke="{MUTED}" stroke-width="1"/></svg>')


def underwater_chart(dd, W=720, H=150, pad=44, color=RED):
    n = len(dd)
    if n < 2:
        return ""
    vmin = min(dd + [0]); span = (0 - vmin) or 1.0
    X = lambda i: pad + i / (n - 1) * (W - 2 * pad)
    Y = lambda v: pad + (0 - v) / span * (H - 2 * pad)
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(dd))
    area = f"{X(0):.1f},{Y(0):.1f} " + pts + f" {X(n-1):.1f},{Y(0):.1f}"
    lab = (f'<text x="{pad-6:.0f}" y="{Y(vmin)+3:.0f}" text-anchor="end" font-size="11" fill="{MUTED}">{money(vmin,1)}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet">'
            f'<line x1="{pad}" y1="{Y(0):.1f}" x2="{W-pad}" y2="{Y(0):.1f}" stroke="{MUTED}" stroke-width="1"/>'
            f'<polygon points="{area}" fill="{color}" fill-opacity="0.22"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>{lab}</svg>')


def bar_chart(labels, values, W=720, H=300, pad=44, dp=1, signed=True):
    n = len(values)
    if n == 0:
        return ""
    vmax = max(values + [0]); vmin = min(values + [0]); span = (vmax - vmin) or 1.0
    Y = lambda v: pad + (vmax - v) / span * (H - 2 * pad)
    zeroY = Y(0); slot = (W - 2 * pad) / n; bw = slot * 0.62
    out = [f'<line x1="{pad}" y1="{zeroY:.1f}" x2="{W-pad}" y2="{zeroY:.1f}" stroke="{MUTED}" stroke-width="1"/>']
    for i, (lab, v) in enumerate(zip(labels, values)):
        cx = pad + slot * (i + 0.5); x = cx - bw / 2
        col = GREEN if v >= 0 else RED
        top = min(Y(v), zeroY); h = abs(Y(v) - zeroY)
        out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{col}" rx="2"/>')
        vy = top - 5 if v >= 0 else top + h + 13
        out.append(f'<text x="{cx:.1f}" y="{vy:.1f}" text-anchor="middle" font-size="11" fill="{INK}">{money(v,dp) if signed else f"{v:.0f}"}</text>')
        out.append(f'<text x="{cx:.1f}" y="{H-pad+16:.0f}" text-anchor="middle" font-size="11" fill="{MUTED}">{esc(lab)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet">{"".join(out)}</svg>'


def weekdays_in_month(year: int, month: int, upto_day: int | None = None) -> int:
    """Mon-Fri count in a month (approx trading days; ignores market holidays)."""
    last = calendar.monthrange(year, month)[1]
    end = min(upto_day, last) if upto_day else last
    return sum(1 for d in range(1, end + 1) if date(year, month, d).weekday() < 5)


def monthly_bar_chart(labels, values, partial_label=None, projection=None,
                      W=720, H=300, pad=44, dp=1):
    """Like bar_chart, but renders `partial_label`'s bar hatched (month-to-date)
    and, if `projection` is given, a dotted pace-projection outline above it."""
    n = len(values)
    if n == 0:
        return ""
    cand = list(values) + [0] + ([projection] if projection is not None else [])
    vmax = max(cand); vmin = min(list(values) + [0]); span = (vmax - vmin) or 1.0
    Y = lambda v: pad + (vmax - v) / span * (H - 2 * pad)
    zeroY = Y(0); slot = (W - 2 * pad) / n; bw = slot * 0.62
    out = [f'<defs>'
           f'<pattern id="hpg" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="{GREEN}" stroke-width="2"/></pattern>'
           f'<pattern id="hpr" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="{RED}" stroke-width="2"/></pattern>'
           f'</defs>'
           f'<line x1="{pad}" y1="{zeroY:.1f}" x2="{W-pad}" y2="{zeroY:.1f}" stroke="{MUTED}" stroke-width="1"/>']
    for i, (lab, v) in enumerate(zip(labels, values)):
        cx = pad + slot * (i + 0.5); x = cx - bw / 2
        col = GREEN if v >= 0 else RED
        is_partial = (lab == partial_label)
        top = min(Y(v), zeroY); h = abs(Y(v) - zeroY)
        if is_partial and projection is not None and abs(projection - v) > 1e-9:
            pj_top = min(Y(projection), zeroY); pj_h = abs(Y(projection) - zeroY)
            out.append(f'<rect x="{x:.1f}" y="{pj_top:.1f}" width="{bw:.1f}" height="{pj_h:.1f}" fill="none" '
                       f'stroke="{col}" stroke-width="1.3" stroke-dasharray="3 3" rx="2" opacity="0.75"/>')
            out.append(f'<text x="{cx:.1f}" y="{pj_top-5:.1f}" text-anchor="middle" font-size="10.5" '
                       f'fill="{MUTED}" font-style="italic">~{money(projection,dp)} proj</text>')
        if is_partial:
            out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{col}" fill-opacity="0.26" rx="2"/>')
            out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="url(#{"hpg" if v>=0 else "hpr"})" rx="2"/>')
            out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="none" stroke="{col}" stroke-dasharray="2 2" rx="2"/>')
        else:
            out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{col}" rx="2"/>')
        vy = top - 5 if v >= 0 else top + h + 13
        out.append(f'<text x="{cx:.1f}" y="{vy:.1f}" text-anchor="middle" font-size="11" fill="{INK}">{money(v,dp)}</text>')
        mlab = esc(lab) + (" ·MTD" if is_partial else "")
        out.append(f'<text x="{cx:.1f}" y="{H-pad+16:.0f}" text-anchor="middle" font-size="11" '
                   f'fill="{AMBER if is_partial else MUTED}">{mlab}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet">{"".join(out)}</svg>'


def stacked_wl_chart(labels, wins, losses, W=720, H=300, pad=44):
    n = len(labels)
    if n == 0:
        return ""
    vmax = max(wins + [0]); vmin = -max(losses + [0]); span = (vmax - vmin) or 1.0
    Y = lambda v: pad + (vmax - v) / span * (H - 2 * pad)
    zeroY = Y(0); slot = (W - 2 * pad) / n; bw = slot * 0.5
    out = [f'<line x1="{pad}" y1="{zeroY:.1f}" x2="{W-pad}" y2="{zeroY:.1f}" stroke="{MUTED}" stroke-width="1"/>']
    for i, lab in enumerate(labels):
        cx = pad + slot * (i + 0.5); x = cx - bw / 2
        wy = Y(wins[i]); out.append(f'<rect x="{x:.1f}" y="{wy:.1f}" width="{bw:.1f}" height="{abs(wy-zeroY):.1f}" fill="{GREEN}" rx="2"/>')
        if wins[i]: out.append(f'<text x="{cx:.1f}" y="{wy-4:.1f}" text-anchor="middle" font-size="11" fill="{GREEN}">{wins[i]}</text>')
        ly = Y(-losses[i]); out.append(f'<rect x="{x:.1f}" y="{zeroY:.1f}" width="{bw:.1f}" height="{abs(ly-zeroY):.1f}" fill="{RED}" rx="2"/>')
        if losses[i]: out.append(f'<text x="{cx:.1f}" y="{ly+13:.1f}" text-anchor="middle" font-size="11" fill="{RED}">{losses[i]}</text>')
        out.append(f'<text x="{cx:.1f}" y="{H-pad+16:.0f}" text-anchor="middle" font-size="10.5" fill="{MUTED}">{esc(lab)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet">{"".join(out)}</svg>'


def histogram(values, bins=18, W=720, H=280, pad=44):
    vals = np.asarray(values, float)
    counts, edges = np.histogram(vals, bins=bins)
    n = len(counts); cmax = max(counts.max(), 1)
    slot = (W - 2 * pad) / n; bw = slot * 0.9
    Y = lambda c: (H - pad) - c / cmax * (H - 2 * pad)
    out = [_axis(W, H, pad)]
    for i, c in enumerate(counts):
        mid = (edges[i] + edges[i + 1]) / 2
        col = GREEN if mid >= 0 else RED
        x = pad + slot * i + (slot - bw) / 2
        out.append(f'<rect x="{x:.1f}" y="{Y(c):.1f}" width="{bw:.1f}" height="{(H-pad)-Y(c):.1f}" fill="{col}" fill-opacity="0.85" rx="1"/>')
    if vals.min() < 0 < vals.max():
        zx = pad + (0 - edges[0]) / (edges[-1] - edges[0]) * (W - 2 * pad)
        out.append(f'<line x1="{zx:.1f}" y1="{pad}" x2="{zx:.1f}" y2="{H-pad}" stroke="{MUTED}" stroke-dasharray="3 3"/>')
    for tick in (edges[0], 0, edges[-1]):
        tx = pad + (tick - edges[0]) / (edges[-1] - edges[0]) * (W - 2 * pad)
        out.append(f'<text x="{tx:.1f}" y="{H-pad+16:.0f}" text-anchor="middle" font-size="11" fill="{MUTED}">{money(tick,1)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet">{"".join(out)}</svg>'


# ---- metric computation ------------------------------------------------------

def compute(df: pd.DataFrame) -> dict:
    pl = df["Exit P/L"].to_numpy(float)
    n = len(pl)
    wins = pl[pl > 0]; losses = pl[pl <= 0]
    cum = np.cumsum(pl); peak = np.maximum.accumulate(cum); dd = cum - peak
    downside = np.sqrt(np.mean(np.clip(pl, None, 0) ** 2))
    std = pl.std(ddof=1) if n > 1 else 0.0
    gross_w = wins.sum(); gross_l = abs(losses.sum())
    win_streaks, loss_streaks = common.streaks(pl)
    episodes = common.drawdown_episodes(pl)
    med_bp = df["Buying Power"].median()
    s = pd.Series(pl)
    return dict(
        n=n, wins=len(wins), losses=len(losses), wr=len(wins) / n * 100 if n else 0,
        total=pl.sum(), avg=pl.mean() if n else 0, std=std,
        avg_w=wins.mean() if len(wins) else 0, avg_l=losses.mean() if len(losses) else 0,
        payoff=(wins.mean() / abs(losses.mean())) if len(losses) and losses.mean() != 0 else float("inf"),
        pf=(gross_w / gross_l) if gross_l else float("inf"),
        sharpe=(pl.mean() / std) if std else 0, sortino=(pl.mean() / downside) if downside else 0,
        maxdd=dd.min() if n else 0, calmar=(pl.sum() / abs(dd.min())) if n and dd.min() < 0 else float("inf"),
        skew=float(s.skew()) if n > 2 else 0, kurt=float(s.kurt()) if n > 3 else 0,
        best=pl.max() if n else 0, worst=pl.min() if n else 0,
        med_bp=med_bp, roc=(pl.mean() / med_bp * 100) if med_bp and med_bp > 0 else float("nan"),
        cum=cum.tolist(), dd=dd.tolist(),
        longest_w=max(win_streaks) if win_streaks else 0, longest_l=max(loss_streaks) if loss_streaks else 0,
        episodes=episodes,
    )


def kpi(label, value, sub="", tone=""):
    color = {"good": GREEN, "bad": RED, "": INK}[tone]
    return (f'<div class="kpi"><div class="kpi-l">{esc(label)}</div>'
            f'<div class="kpi-v" style="color:{color}">{value}</div>'
            f'<div class="kpi-s">{esc(sub)}</div></div>')


def table(headers, rows, right_from=1):
    th = "".join(f'<th{" class=r" if i>=right_from else ""}>{esc(h)}</th>' for i, h in enumerate(headers))
    trs = ""
    for r in rows:
        tds = "".join(f'<td{" class=r" if i>=right_from else ""}>{c}</td>' for i, c in enumerate(r))
        trs += f"<tr>{tds}</tr>"
    return f'<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


# ---- trade ledger (Trades tab) ----------------------------------------------

LEDGER_COLS = ["#", "Date", "Day", "In", "Out", "Hold", "Exit", "Credit", "Target",
               "P/L", "Ret%", "Cum", "IVR%", "SPX", "Strikes", "Notes"]
LEDGER_RIGHT = {"#", "In", "Out", "Hold", "Credit", "Target", "P/L", "Ret%", "Cum", "IVR%", "SPX"}
_BADGE = {"PROFIT-TARGET": ("PT", "pt"), "TIME-STOP": ("TIME", "ts"), "SETTLED": ("SETTLE", "st")}


def ledger_table(df: pd.DataFrame) -> str:
    head = "".join(
        f'<th onclick="sortT(this)"{" class=r" if h in LEDGER_RIGHT else ""}>{esc(h)}<span class="arr"></span></th>'
        for h in LEDGER_COLS)
    rows = []
    cum = 0.0
    for i, (_, r) in enumerate(df.iterrows()):
        pl = float(r["Exit P/L"]); cum += pl
        bp = r["Buying Power"]; ret = (pl / bp * 100) if bp and bp > 0 else None
        reason = r["reason"]; lbl, cls = _BADGE.get(reason, (reason, "ts"))
        hold = r["hold"]
        sc, lc, sp, lp = (parse_strike(r["Short Call"]), parse_strike(r["Long Call"]),
                          parse_strike(r["Short Put"]), parse_strike(r["Long Put"]))
        strikes = (f"C {sc:g}›{lc:g} · P {sp:g}›{lp:g}"
                   if None not in (sc, lc, sp, lp) else "—")
        ivr = ivr_display(r["IV Rank"]); spx = r["SPX Spot"]
        plc = GREEN if pl >= 0 else RED
        di = int(str(r["Date"]).replace("-", ""))

        def td(v_sort, disp, cls_extra=""):
            return f'<td class="r{cls_extra}" data-v="{v_sort}">{disp}</td>'

        cells = [
            td(i + 1, i + 1),
            f'<td data-v="{di}">{esc(r["Date"])}</td>',
            f'<td data-v="{DOW_IDX.get(r["DOW"],0)}">{esc(str(r["DOW"])[:3])}</td>',
            td(mins_of(r["Entry Time"]), esc(str(r["Entry Time"])[:5])),
            td(mins_of(r["Exit Time"]), esc(str(r["Exit Time"])[:5])),
            td(hold if hold is not None else "", hold if hold is not None else "—"),
            f'<td data-v="{["PROFIT-TARGET","TIME-STOP","SETTLED"].index(reason) if reason in _BADGE else 9}">'
            f'<span class="badge {cls}">{lbl}</span></td>',
            td(f'{r["Credit Collected"]:.2f}', f'{r["Credit Collected"]:.2f}'),
            td(f'{r["Profit Target"]:.2f}', f'{r["Profit Target"]:.2f}'),
            f'<td class="r" data-v="{pl}" style="color:{plc};font-weight:600">{money(pl)}</td>',
            td(ret if ret is not None else "", f'{ret:+.2f}%' if ret is not None else "—"),
            f'<td class="r" data-v="{cum:.2f}" style="color:{GREEN if cum>=0 else RED}">{money(cum)}</td>',
            td(f'{ivr:.0f}' if ivr is not None else "", f'{ivr:.0f}%' if ivr is not None else "—"),
            td(f'{spx:.0f}' if pd.notna(spx) else "", f'{spx:.0f}' if pd.notna(spx) else "—"),
            f'<td class="mono">{esc(strikes)}</td>',
            f'<td class="muted" title="{esc(r["Notes"])}">{esc(str(r["Notes"])[:46])}</td>',
        ]
        rows.append(f'<tr data-reason="{reason}" data-pl="{pl}">{"".join(cells)}</tr>')
    return (f'<div class="tbl-wrap"><table id="tradesTable">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


# ---- page assembly -----------------------------------------------------------

def build_html(strategy: str, df: pd.DataFrame) -> str:
    m = compute(df)
    df = df.copy()
    df["reason"] = df.apply(common.classify_exit, axis=1)
    df["hold"] = df.apply(common.hold_minutes, axis=1)

    er_rows, er_labels, er_pl = [], [], []
    for r in ["PROFIT-TARGET", "TIME-STOP", "SETTLED"]:
        g = df[df["reason"] == r]
        if len(g) == 0:
            continue
        gpl = g["Exit P/L"]
        er_labels.append(r.replace("-", "‑")); er_pl.append(round(gpl.sum(), 2))
        er_rows.append([r, len(g), f'{(gpl>0).sum()}/{(gpl<=0).sum()}', money(gpl.mean()),
                        f'<b style="color:{GREEN if gpl.sum()>=0 else RED}">{money(gpl.sum())}</b>'])

    def hold_bucket(row):
        if row["reason"] == "SETTLED" or row["hold"] is None:
            return "settle"
        for hi, lab in [(30, "<30m"), (60, "30-60m"), (120, "1-2h"), (180, "2-3h"), (240, "3-4h"), (360, "4-6h")]:
            if row["hold"] < hi:
                return lab
        return "settle"
    df["hb"] = df.apply(hold_bucket, axis=1)
    hb_lab, hb_w, hb_l = [], [], []
    for lab in ["<30m", "30-60m", "1-2h", "2-3h", "3-4h", "4-6h", "settle"]:
        g = df[df["hb"] == lab]
        if len(g) == 0:
            continue
        hb_lab.append(lab); hb_w.append(int((g["Exit P/L"] > 0).sum())); hb_l.append(int((g["Exit P/L"] <= 0).sum()))

    dow_lab, dow_pl, dow_rows = [], [], []
    for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        g = df[df["DOW"] == d]
        if len(g) == 0:
            continue
        gpl = g["Exit P/L"]
        dow_lab.append(d[:3]); dow_pl.append(round(gpl.sum(), 2))
        dow_rows.append([d, len(g), f'{(gpl>0).mean()*100:.0f}%', money(gpl.mean()), money(gpl.sum())])

    mo = df.groupby("Month")["Exit P/L"].agg(["size", "sum", "mean"])
    mo_lab = list(mo.index); mo_pl = [round(x, 2) for x in mo["sum"]]
    cur_month = datetime.now().strftime("%Y-%m")
    partial_month = cur_month if cur_month in set(mo_lab) else None
    projection = None
    if partial_month:
        yy, mm = int(cur_month[:4]), int(cur_month[5:7])
        elapsed = weekdays_in_month(yy, mm, datetime.now().day)
        total = weekdays_in_month(yy, mm)
        s = float(mo.loc[cur_month, "sum"])
        if elapsed > 0 and total > elapsed:
            projection = round(s / elapsed * total, 2)
    mo_rows = [[f"{ix} ·MTD" if ix == partial_month else ix, int(r["size"]),
                money(r["mean"]), money(r["sum"])] for ix, r in mo.iterrows()]

    cols = ["Date", "Entry Time", "Exit Time", "reason", "Exit P/L", "Notes"]
    def trade_rows(sub):
        out = []
        for _, r in sub.iterrows():
            pl = r["Exit P/L"]
            out.append([esc(r["Date"]), esc(str(r["Entry Time"])[:5]), esc(str(r["Exit Time"])[:5]),
                        esc(r["reason"]), f'<b style="color:{GREEN if pl>=0 else RED}">{money(pl)}</b>',
                        esc(str(r["Notes"])[:60])])
        return out
    best = trade_rows(df.nlargest(5, "Exit P/L")[cols])
    worst = trade_rows(df.nsmallest(5, "Exit P/L")[cols])

    d0, d1 = df["Date"].min(), df["Date"].max()
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    kpis = "".join([
        kpi("Net P/L", money(m["total"]), f'{m["n"]} trades', "good" if m["total"] >= 0 else "bad"),
        kpi("Win rate", f'{m["wr"]:.1f}%', f'{m["wins"]}W / {m["losses"]}L'),
        kpi("Expectancy", money(m["avg"]), "avg / trade", "good" if m["avg"] >= 0 else "bad"),
        kpi("Profit factor", f'{m["pf"]:.2f}', "gross W / gross L"),
        kpi("Payoff", f'{m["payoff"]:.2f}', "avgW / |avgL|"),
        kpi("Max drawdown", money(m["maxdd"]), f'Calmar {m["calmar"]:.1f}', "bad"),
        kpi("Sharpe / trade", f'{m["sharpe"]:.2f}', f'Sortino {m["sortino"]:.2f}'),
        kpi("Return on capital", f'{m["roc"]:.2f}%', f'/ trade · {money(m["med_bp"],0)} BP'),
        kpi("Avg win / loss", f'{money(m["avg_w"])} / {money(m["avg_l"])}', f'best {money(m["best"])} · worst {money(m["worst"])}'),
        kpi("Longest streak", f'{m["longest_w"]}W', f'longest losing {m["longest_l"]}L'),
        kpi("Skew / kurtosis", f'{m["skew"]:+.2f} / {m["kurt"]:.2f}', "shape of P/L"),
        kpi("Std dev", money(m["std"]), "per-trade σ"),
    ])

    def panel(title, body, sub=""):
        s = f'<div class="sub">{esc(sub)}</div>' if sub else ""
        return f'<section class="panel"><h2>{esc(title)}</h2>{s}{body}</section>'

    dd_eps = sorted(m["episodes"])[:1]
    worst_ep = f'{money(dd_eps[0][0])} over {dd_eps[0][1]} trades' if dd_eps else "—"

    overview = f"""<div class="kpis">{kpis}</div>
{panel("Equity curve (cumulative P/L)", area_chart(m["cum"], color=GREEN if m["total"]>=0 else RED)
       + '<div style="height:8px"></div>' + underwater_chart(m["dd"]),
       f'Climb to {money(m["total"])}. Underwater plot shows drawdowns — worst episode {worst_ep}, max {money(m["maxdd"])}.')}
<div class="grid">
{panel("Monthly P/L", monthly_bar_chart(mo_lab, mo_pl, partial_label=partial_month, projection=projection),
       "Hatched bar = current month-to-date (partial); dotted outline = pace projection if the rest of the month trades at the same daily rate (approx — ignores holidays)." if partial_month else "")}
{panel("P/L by day of week", bar_chart(dow_lab, dow_pl))}
{panel("Exit-reason decomposition", bar_chart(er_labels, er_pl) + table(["Reason","n","W/L","Avg","Total"], er_rows),
       "How every trade ends. This is where the edge comes from.")}
{panel("Outcome by hold time", stacked_wl_chart(hb_lab, hb_w, hb_l)
       + '<div class="legend"><span><span class="dot" style="background:'+GREEN+'"></span>wins</span>'
         '<span><span class="dot" style="background:'+RED+'"></span>losses</span></div>',
       "Wins up, losses down. The longer a position is held, the worse it gets.")}
</div>
{panel("P/L distribution (per trade)", histogram(df["Exit P/L"].tolist()), "Each bar = number of trades in that P/L range.")}
<div class="grid">
{panel("Monthly detail", table(["Month","n","Avg","Total"], mo_rows))}
{panel("Day-of-week detail", table(["Day","n","Win%","Avg","Total"], dow_rows))}
{panel("Top 5 winners", table(["Date","In","Out","Exit","P/L","Notes"], best))}
{panel("Worst 5", table(["Date","In","Out","Exit","P/L","Notes"], worst))}
</div>"""

    trades = f"""<section class="panel">
  <h2>Trade ledger — every trade & its metrics</h2>
  <div class="sub">Chronological. Click any column header to sort; tap a chip to filter. <b>Cum</b> is running cumulative P/L in entry order; <b>Ret%</b> = P/L ÷ buying power; <b>Target</b> = profit-target debit; <b>Strikes</b> = call short›long · put short›long.</div>
  <div id="filters">
    <button class="chip on" onclick="filt('all',this)">All</button>
    <button class="chip" onclick="filt('win',this)">Wins</button>
    <button class="chip" onclick="filt('loss',this)">Losses</button>
    <button class="chip" onclick="filt('PROFIT-TARGET',this)">Profit-target</button>
    <button class="chip" onclick="filt('TIME-STOP',this)">Time-stop</button>
    <button class="chip" onclick="filt('SETTLED',this)">Settled</button>
    <span id="summary" class="summary"></span>
  </div>
  {ledger_table(df)}
</section>"""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(strategy)} — Performance Dashboard</title>
<style>
:root{{color-scheme:dark}} *{{box-sizing:border-box}}
body{{margin:0;background:{BG};color:{INK};font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 18px 60px}}
header h1{{margin:0 0 2px;font-size:24px}} header .meta{{color:{MUTED};font-size:13px}}
.tabs{{display:flex;gap:4px;margin:18px 0 18px;border-bottom:1px solid {GRID}}}
.tab{{background:none;border:0;color:{MUTED};padding:9px 16px;font-size:14px;cursor:pointer;border-bottom:2px solid transparent;border-radius:0}}
.tab.on{{color:{INK};border-bottom-color:{BLUE};font-weight:600}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:0 0 16px}}
.kpi{{background:{PANEL};border:1px solid {GRID};border-radius:12px;padding:14px 16px}}
.kpi-l{{color:{MUTED};font-size:12px;text-transform:uppercase;letter-spacing:.4px}}
.kpi-v{{font-size:22px;font-weight:650;margin:3px 0}} .kpi-s{{color:{MUTED};font-size:12px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:780px){{.grid{{grid-template-columns:1fr}}}}
.panel{{background:{PANEL};border:1px solid {GRID};border-radius:12px;padding:16px 18px;margin-bottom:16px}}
.panel h2{{margin:0 0 2px;font-size:15px}} .panel .sub{{color:{MUTED};font-size:12px;margin-bottom:10px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}}
th,td{{padding:7px 9px;border-bottom:1px solid {GRID};text-align:left;white-space:nowrap}}
th{{color:{MUTED};font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.3px}}
td.r,th.r{{text-align:right}} tbody tr:hover{{background:#1c2430}}
.note{{color:{MUTED};font-size:12px;background:#12181f;border:1px solid {GRID};border-left:3px solid {AMBER};border-radius:8px;padding:10px 12px;margin-top:14px}}
.legend span{{display:inline-block;margin-right:14px;color:{MUTED};font-size:12px}}
.dot{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:middle}}
#filters{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 12px}}
.chip{{background:{PANEL};border:1px solid {GRID};color:{MUTED};border-radius:999px;padding:6px 13px;font-size:13px;cursor:pointer}}
.chip.on{{color:{INK};border-color:{BLUE};background:#13233a}}
.summary{{color:{MUTED};font-size:13px;margin-left:auto}}
.tbl-wrap{{overflow-x:auto;border:1px solid {GRID};border-radius:10px}}
#tradesTable{{font-size:12.5px;min-width:1080px;margin:0}}
#tradesTable th{{position:sticky;top:0;background:#10161d;cursor:pointer;user-select:none;z-index:1}}
#tradesTable th:hover{{color:{INK}}} #tradesTable th .arr{{font-size:10px;margin-left:3px;color:{BLUE}}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}}
.badge.pt{{background:rgba(63,185,80,.15);color:{GREEN}}}
.badge.ts{{background:rgba(210,153,34,.18);color:{AMBER}}}
.badge.st{{background:rgba(248,81,73,.15);color:{RED}}}
td.mono{{font-family:ui-monospace,Menlo,monospace;color:#aab2bd;font-size:12px}}
td.muted{{color:{MUTED};max-width:260px;overflow:hidden;text-overflow:ellipsis}}
</style></head><body><div class="wrap">
<header>
  <h1>{esc(strategy)} <span style="color:{MUTED};font-weight:400">· performance dashboard</span></h1>
  <div class="meta">{m['n']} closed trades · {esc(d0)} → {esc(d1)} · paper trading · generated {gen}</div>
</header>
<div class="tabs">
  <button class="tab on" id="tab-overview" onclick="showTab('overview',this)">Overview</button>
  <button class="tab" id="tab-trades" onclick="showTab('trades',this)">Trades ({m['n']})</button>
</div>
<div class="view" id="view-overview">{overview}</div>
<div class="view" id="view-trades" style="display:none">{trades}</div>
<div class="note"><b>Read me.</b> P/L is in the trade log's native per-1-lot units. Paper-trading results (fills via REST mark prices, no real slippage).
Rows tagged <i>auto-expired</i> are synthetic max-loss stamps from the stale-trade cleanup, not real fills.
<b>IVR%</b> is best-effort normalised — the IV Rank column is inconsistently scaled (a known data-quality issue), so treat it as approximate.
Regenerate: <code>venv/bin/python analysis/strategy_dashboard.py "{esc(strategy)}"</code></div>
</div>
<script>
function showTab(name,btn){{
  document.querySelectorAll('.view').forEach(v=>v.style.display='none');
  document.getElementById('view-'+name).style.display='';
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  btn.classList.add('on');
}}
function sortT(th){{
  var table=th.closest('table'), tb=table.tBodies[0], rows=Array.prototype.slice.call(tb.rows);
  var idx=Array.prototype.indexOf.call(th.parentNode.children,th);
  var dir=th.getAttribute('data-dir')==='asc'?'desc':'asc';
  Array.prototype.forEach.call(th.parentNode.children,function(h){{h.removeAttribute('data-dir');var a=h.querySelector('.arr');if(a)a.textContent='';}});
  th.setAttribute('data-dir',dir); var arr=th.querySelector('.arr'); if(arr)arr.textContent=dir==='asc'?'▲':'▼';
  rows.sort(function(a,b){{
    var av=a.cells[idx].getAttribute('data-v'), bv=b.cells[idx].getAttribute('data-v');
    var an=parseFloat(av), bn=parseFloat(bv), c;
    if(!isNaN(an)||!isNaN(bn)){{ an=isNaN(an)?-Infinity:an; bn=isNaN(bn)?-Infinity:bn; c=an-bn; }}
    else {{ c=(a.cells[idx].textContent).localeCompare(b.cells[idx].textContent); }}
    return dir==='asc'?c:-c;
  }});
  rows.forEach(function(r){{tb.appendChild(r);}});
}}
function filt(kind,btn){{
  document.querySelectorAll('#filters .chip').forEach(function(c){{c.classList.remove('on');}});
  btn.classList.add('on');
  var n=0,pl=0,w=0;
  document.querySelectorAll('#tradesTable tbody tr').forEach(function(r){{
    var p=parseFloat(r.getAttribute('data-pl'));
    var show = kind==='all' || (kind==='win'&&p>0) || (kind==='loss'&&p<=0) || r.getAttribute('data-reason')===kind;
    r.style.display=show?'':'none';
    if(show){{n++;pl+=p;if(p>0)w++;}}
  }});
  var pls=(pl<0?'-$'+Math.abs(pl).toFixed(2):'$'+pl.toFixed(2));
  document.getElementById('summary').textContent='Showing '+n+' · Net '+pls+' · Win '+(n?(100*w/n).toFixed(1):0)+'%';
}}
document.addEventListener('DOMContentLoaded',function(){{filt('all',document.querySelector('#filters .chip'));}});
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("strategy")
    ap.add_argument("--out", default=None)
    ap.add_argument("--open", action="store_true", help="open in browser after writing")
    ap.add_argument("--include-private", action="store_true")
    args = ap.parse_args()

    df = common.load_trades(drop_private=not args.include_private, drop_outliers=True)
    df = df[df["Strategy"] == args.strategy].copy()
    if df.empty:
        df2 = common.load_trades(drop_private=False, drop_outliers=True)
        df = df2[df2["Strategy"] == args.strategy].copy()
    if df.empty:
        sys.exit(f"No closed trades found for strategy '{args.strategy}'.")

    out = Path(args.out) if args.out else (common.PROJECT_ROOT / "analysis" /
            f"dashboard_{args.strategy.replace(' ', '_').replace('/', '-')}.html")
    out.write_text(build_html(args.strategy, df), encoding="utf-8")
    print(f"Wrote {out}  ({len(df)} trades)")
    if args.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
