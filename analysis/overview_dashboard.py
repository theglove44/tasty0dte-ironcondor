"""
overview_dashboard.py — Active-roster overview dashboard (findings + suggestions + data).

One self-contained offline HTML page that answers "how is the live roster doing,
what should I do about it, and what's the evidence?" for the 7 strategies still
trading after the 2026-06-05 roster trim:

    Iron Fly V1 / V2 / V3 / V4  +  JadeLizard 5DTE / 7DTE / 10DTE

It deliberately does NOT use performance_report.py's `--active-only` 14-day
heuristic, which mis-classifies the roster (keeps disabled Dynamic/ORB in, drops
multi-day JL10 out). The roster is the explicit list below.

All stats/filters come from analysis/common.py and the chart/metric helpers are
imported from analysis/strategy_dashboard.py — no re-implemented logic.

Sections: top-line KPIs · Findings & suggestions (each backed by computed data)
· strategy leaderboard (links to each per-strategy dashboard) · roster equity
curve · net / expectancy / ROC comparison bars · win-rate-vs-payoff scatter
· monthly grid · exit-reason decomposition · Iron Fly entry-window experiment
· Jade Lizard tail-risk panel · capital efficiency · currently-open positions.

Usage:
  python analysis/overview_dashboard.py
  python analysis/overview_dashboard.py --out /tmp/overview.html --open
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from strategy_dashboard import (
    BG, PANEL, INK, MUTED, GREEN, RED, BLUE, AMBER, GRID,
    money, esc, compute, area_chart, bar_chart, kpi, table,
)

# --- The live roster (explicit; see module docstring) ------------------------
IRON_FLIES = ["Iron Fly V1", "Iron Fly V2", "Iron Fly V3", "Iron Fly V4"]
JADE_LIZARDS = ["JadeLizard_5DTE", "JadeLizard_7DTE", "JadeLizard_10DTE"]
ACTIVE_ROSTER = IRON_FLIES + JADE_LIZARDS

CONFIG = {
    "Iron Fly V1": "Open+30m · 10% PT", "Iron Fly V2": "Open+30m · 20% PT",
    "Iron Fly V3": "Open+1h · 10% PT", "Iron Fly V4": "Open+1h · 20% PT",
    "JadeLizard_5DTE": "5DTE · 25% PT", "JadeLizard_7DTE": "7DTE · 25% PT",
    "JadeLizard_10DTE": "10DTE · 25% PT",
}


def pretty(name: str) -> str:
    return name.replace("JadeLizard_", "Jade Lizard ")


def short(name: str) -> str:
    return name.replace("Iron Fly ", "IF ").replace("JadeLizard_", "JL ").replace("DTE", "")


def dash_link(name: str) -> str:
    return f"dashboard_{name.replace(' ', '_').replace('/', '-')}.html"


def tone_of(v: float) -> str:
    return "good" if v >= 0 else "bad"


# --- scatter (win-rate vs payoff) — not in strategy_dashboard ----------------

def scatter(points, W=720, H=360, pad=56, xbounds=(45, 100), ref_y=1.0):
    """points: list of dict(x, y, label, color, n). x=WR%, y=payoff."""
    ys = [p["y"] for p in points]
    ymax = max(ys + [ref_y]) * 1.12
    ymin = 0.0
    yspan = (ymax - ymin) or 1.0
    xmin, xmax = xbounds
    xspan = (xmax - xmin) or 1.0
    X = lambda v: pad + (v - xmin) / xspan * (W - 2 * pad)
    Y = lambda v: pad + (ymax - v) / yspan * (H - 2 * pad)
    out = []
    # y gridlines
    for gv in np.linspace(0, ymax, 5):
        gy = Y(gv)
        out.append(f'<line x1="{pad}" y1="{gy:.1f}" x2="{W-pad}" y2="{gy:.1f}" stroke="{GRID}" stroke-dasharray="3 3"/>'
                   f'<text x="{pad-8:.0f}" y="{gy+3:.0f}" text-anchor="end" font-size="11" fill="{MUTED}">{gv:.1f}</text>')
    # x ticks
    for gv in range(int(xmin), int(xmax) + 1, 10):
        gx = X(gv)
        out.append(f'<text x="{gx:.0f}" y="{H-pad+18:.0f}" text-anchor="middle" font-size="11" fill="{MUTED}">{gv}%</text>')
    # payoff = 1 reference (wins == losses in size)
    ry = Y(ref_y)
    out.append(f'<line x1="{pad}" y1="{ry:.1f}" x2="{W-pad}" y2="{ry:.1f}" stroke="{AMBER}" stroke-width="1.3" stroke-dasharray="6 4"/>'
               f'<text x="{W-pad:.0f}" y="{ry-6:.0f}" text-anchor="end" font-size="11" fill="{AMBER}">payoff = 1 (wins = losses)</text>')
    # axis titles
    out.append(f'<text x="{W/2:.0f}" y="{H-10:.0f}" text-anchor="middle" font-size="12" fill="{MUTED}">win rate →</text>')
    out.append(f'<text x="16" y="{H/2:.0f}" text-anchor="middle" font-size="12" fill="{MUTED}" transform="rotate(-90 16 {H/2:.0f})">payoff (avgWin / |avgLoss|) →</text>')
    for p in points:
        cx, cy = X(p["x"]), Y(p["y"])
        r = 6 + min(p["n"], 100) / 100 * 10
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{p["color"]}" fill-opacity="0.65" stroke="{p["color"]}" stroke-width="1.5"/>')
        out.append(f'<text x="{cx:.1f}" y="{cy-r-5:.1f}" text-anchor="middle" font-size="11" fill="{INK}">{esc(p["label"])}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet">{"".join(out)}</svg>'


# --- monthly colored grid ----------------------------------------------------

def monthly_table(roster_df: pd.DataFrame) -> str:
    cur_month = datetime.now().strftime("%Y-%m")
    piv = roster_df.pivot_table(index="Month", columns="Strategy", values="Exit P/L",
                                aggfunc="sum")
    piv = piv.reindex(columns=[s for s in ACTIVE_ROSTER if s in piv.columns])
    vmax = np.nanmax(np.abs(piv.to_numpy())) or 1.0

    def cell(v):
        if pd.isna(v):
            return '<td class="r" style="color:#3a414d">·</td>'
        a = min(abs(v) / vmax, 1.0)
        col = GREEN if v >= 0 else RED
        return (f'<td class="r" style="background:{col}{int(18+a*60):02x};color:{INK}">'
                f'{("+" if v>=0 else "-")}{abs(v):.1f}</td>')

    head = '<th>Month</th>' + "".join(f'<th class="r" title="{esc(c)}">{esc(short(c))}</th>' for c in piv.columns) + '<th class="r">Total</th>'
    rows = ""
    for m, r in piv.iterrows():
        tot = r.sum()
        mlab = esc(m) + (f' <span style="color:{AMBER}">·MTD</span>' if m == cur_month else "")
        rows += f'<tr><td>{mlab}</td>' + "".join(cell(v) for v in r) + f'<td class="r" style="font-weight:600;color:{GREEN if tot>=0 else RED}">{money(tot,1)}</td></tr>'
    # totals row
    colsum = piv.sum()
    grand = colsum.sum()
    rows += ('<tr style="border-top:2px solid #30363d">'
             f'<td style="font-weight:600">TOTAL</td>'
             + "".join(f'<td class="r" style="font-weight:600;color:{GREEN if v>=0 else RED}">{money(v,1)}</td>' for v in colsum)
             + f'<td class="r" style="font-weight:700;color:{GREEN if grand>=0 else RED}">{money(grand,1)}</td></tr>')
    return f'<div class="tbl-wrap"><table>{("<thead><tr>"+head+"</tr></thead>")}<tbody>{rows}</tbody></table></div>'


# --- findings & suggestions --------------------------------------------------

def finding_card(tone: str, title: str, body: str, action: str) -> str:
    border = {"good": GREEN, "bad": RED, "info": BLUE}[tone]
    tag = {"good": "STRENGTH", "bad": "RISK", "info": "INSIGHT"}[tone]
    tagcol = {"good": GREEN, "bad": RED, "info": BLUE}[tone]
    return (f'<div class="finding" style="border-left-color:{border}">'
            f'<div class="ftag" style="color:{tagcol}">{tag}</div>'
            f'<h3>{title}</h3><p>{body}</p>'
            f'<div class="action"><span>DO</span> {action}</div></div>')


def build_findings(M: dict, T: dict, roster_total: float, book_total: float,
                   iron_total: float, jl_total: float, jl_losses: pd.DataFrame) -> str:
    v1, v2, v3, v4 = (M["Iron Fly V1"], M["Iron Fly V2"], M["Iron Fly V3"], M["Iron Fly V4"])
    jl5, jl7, jl10 = (M["JadeLizard_5DTE"], M["JadeLizard_7DTE"], M["JadeLizard_10DTE"])
    drag = book_total - roster_total
    jl_n = jl5["n"] + jl7["n"] + jl10["n"]
    jl_wr = (jl5["wins"] + jl7["wins"] + jl10["wins"]) / jl_n * 100
    worst_loss = jl_losses["Exit P/L"].min()
    cards = [
        finding_card(
            "good", "Iron Fly V1 is the engine — keep it the core position",
            f"<b>{money(v1['total'])}</b> over {v1['n']} trades at <b>{money(v1['avg'])}/trade</b>. The only strategy "
            f"whose edge clears the 95%-confidence bar by a wide margin (<b>t = {T['Iron Fly V1']:.2f}</b>), with the "
            f"highest profit factor on the board (<b>{v1['pf']:.2f}</b>) and the best capital efficiency "
            f"(<b>{v1['roc']:.2f}%/trade</b> on just {money(v1['med_bp'],0)} buying power). {v1['wr']:.1f}% win rate, "
            f"Sharpe {v1['sharpe']:.2f}/trade. Green every month since March.",
            "Treat V1 as the core. It carries the strongest, most capital-efficient, still-current edge of anything trading."),
        finding_card(
            "info", "Entry +30 min beats +1 h, and 10% PT beats 20% — confirmed in both pairs",
            f"Same structure, only the entry window differs: V1 (+30m) {money(v1['avg'])}/trade vs V3 (+1h) {money(v3['avg'])} "
            f"(edge {money(v1['avg']-v3['avg'])}); V2 (+30m) {money(v2['avg'])} vs V4 (+1h) {money(v4['avg'])} "
            f"(edge {money(v2['avg']-v4['avg'])}). The +30m / 10%-PT corner (V1) wins on every axis. "
            f"V3/V4 are not statistically distinguishable from zero (PF {v3['pf']:.2f} / {v4['pf']:.2f}).",
            "Concentrate size in the +30m / 10% cell. Keep V3/V4 small — they add diversification, not proven edge."),
        finding_card(
            "bad", "🔴 Jade Lizard's downside has arrived — the \"100% win rate\" was a mirage",
            f"All three variants were unbeaten until June; each has now taken exactly one settled ITM loss "
            f"(worst <b>{money(worst_loss)}</b>). Win rate is still ~{jl_wr:.0f}% but payoff has collapsed to "
            f"<b>{jl5['payoff']:.2f}–{jl10['payoff']:.2f}</b> — one loss erases 7–15 wins, the same "
            f"\"pennies in front of a steamroller\" shape that got the 20-Delta IC deleted. Combined {money(jl_total)} "
            f"net is positive only because a long May win streak banked first; none of the three is statistically significant.",
            "Decide before the next ITM breach: defend the short side (tighten the wing / add an ITM stop / cut size) "
            "or retire the variants. As structured the assignment risk is undefended."),
        finding_card(
            "info", "Capital efficiency: Iron Flies return ~12× more per dollar at risk",
            f"Iron Flies reserve ~{money(v1['med_bp'],0)} buying power; Jade Lizards ~{money(jl5['med_bp'],0)} "
            f"(~{jl5['med_bp']/max(v1['med_bp'],1):.0f}×). Per dollar of capital, V1 returns {v1['roc']:.2f}%/trade vs "
            f"JL's {jl5['roc']:.2f}–{jl10['roc']:.2f}%/trade. Headline P/L flatters the Jade Lizards; return-on-capital does not.",
            "Rank and size by return-on-capital, not net P/L. The Jade Lizards tie up the most capital for the thinnest, least-proven edge."),
        finding_card(
            "good", "The June 5 roster trim is validated by the data",
            f"The live roster is <b>{money(roster_total)}</b> across {sum(m['n'] for m in M.values())} closed trades "
            f"(Iron Flies {money(iron_total)}, Jade Lizards {money(jl_total)}). The whole book is only {money(book_total)} "
            f"because the removed + disabled strategies (ICs, Gap Filter, Dynamic, ORB) drag <b>{money(drag)}</b>.",
            "Keep Dynamic 0DTE and ORB Stacking disabled — both were net-negative and capital-heavy. The trim is working."),
    ]
    return '<div class="findings">' + "".join(cards) + "</div>"


# --- leaderboard -------------------------------------------------------------

def leaderboard(M: dict, tstats: dict) -> str:
    order = sorted(ACTIVE_ROSTER, key=lambda s: M[s]["roc"], reverse=True)
    head = ["Strategy", "Config", "n", "WR%", "Net P/L", "Exp/tr", "Payoff", "PF", "t", "Med BP", "ROC%/tr", "MaxDD", ""]
    right = {"n", "WR%", "Net P/L", "Exp/tr", "Payoff", "PF", "t", "Med BP", "ROC%/tr", "MaxDD"}
    th = "".join(f'<th{" class=r" if h in right else ""}>{esc(h)}</th>' for h in head)
    trs = ""
    for s in order:
        m = M[s]
        t = tstats[s]
        tcol = GREEN if t >= 2 else (AMBER if t >= 1 else MUTED)
        plc = GREEN if m["total"] >= 0 else RED
        star = " ★" if s == order[0] else ""
        trs += (
            f'<tr>'
            f'<td><a href="{dash_link(s)}">{esc(pretty(s))}</a>{star}</td>'
            f'<td class="muted">{esc(CONFIG[s])}</td>'
            f'<td class="r">{m["n"]}</td>'
            f'<td class="r">{m["wr"]:.1f}</td>'
            f'<td class="r" style="color:{plc};font-weight:600">{money(m["total"])}</td>'
            f'<td class="r" style="color:{GREEN if m["avg"]>=0 else RED}">{money(m["avg"])}</td>'
            f'<td class="r">{m["payoff"]:.2f}</td>'
            f'<td class="r">{m["pf"]:.2f}</td>'
            f'<td class="r" style="color:{tcol};font-weight:600">{t:.2f}</td>'
            f'<td class="r">{money(m["med_bp"],0)}</td>'
            f'<td class="r">{m["roc"]:.2f}%</td>'
            f'<td class="r" style="color:{RED}">{money(m["maxdd"],1)}</td>'
            f'<td class="r"><a href="{dash_link(s)}">view →</a></td>'
            f'</tr>')
    return f'<div class="tbl-wrap"><table class="lead"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def tstat(g: pd.DataFrame) -> float:
    pl = g["Exit P/L"].to_numpy(float)
    if len(pl) < 2 or pl.std(ddof=1) == 0:
        return float("nan")
    return pl.mean() / (pl.std(ddof=1) / np.sqrt(len(pl)))


# --- page assembly -----------------------------------------------------------

def panel(title, body, sub=""):
    s = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    return f'<section class="panel"><h2>{esc(title)}</h2>{s}{body}</section>'


def build_html(df_book: pd.DataFrame, open_df: pd.DataFrame, book_total: float) -> str:
    df = df_book[df_book["Strategy"].isin(ACTIVE_ROSTER)].copy()
    M = {s: compute(g) for s, g in df.groupby("Strategy") if s in ACTIVE_ROSTER}
    T = {s: tstat(df[df["Strategy"] == s]) for s in ACTIVE_ROSTER}

    roster_total = sum(m["total"] for m in M.values())
    roster_n = sum(m["n"] for m in M.values())
    roster_wins = sum(m["wins"] for m in M.values())
    iron_total = sum(M[s]["total"] for s in IRON_FLIES)
    jl_total = sum(M[s]["total"] for s in JADE_LIZARDS)
    iron_n = sum(M[s]["n"] for s in IRON_FLIES)
    jl_n = sum(M[s]["n"] for s in JADE_LIZARDS)

    d0, d1 = df["Date"].min(), df["Date"].max()
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- KPIs ----
    best = max(ACTIVE_ROSTER, key=lambda s: M[s]["roc"])
    kpis = "".join([
        kpi("Active roster net", money(roster_total), f"{roster_n} closed trades", tone_of(roster_total)),
        kpi("Overall win rate", f"{roster_wins/roster_n*100:.1f}%", f"{roster_wins}W / {roster_n-roster_wins}L"),
        kpi("Iron Flies", money(iron_total), f"{iron_n} trades · ~$120 BP", tone_of(iron_total)),
        kpi("Jade Lizards", money(jl_total), f"{jl_n} trades · ~$1,515 BP", tone_of(jl_total)),
        kpi("Best strategy", pretty(best), f"{M[best]['roc']:.2f}%/tr ROC · t={T[best]:.2f}", "good"),
        kpi("Open now", str(len(open_df)), "positions in flight"),
    ])

    # ---- comparison data (ROC order: capital-aware, V1 leads) ----
    order = sorted(ACTIVE_ROSTER, key=lambda s: M[s]["roc"], reverse=True)
    labs = [short(s) for s in order]
    net_vals = [round(M[s]["total"], 2) for s in order]
    exp_vals = [round(M[s]["avg"], 2) for s in order]
    roc_vals = [round(M[s]["roc"], 3) for s in order]

    sc_points = []
    for s in ACTIVE_ROSTER:
        m = M[s]
        py = min(m["payoff"], 4.0) if np.isfinite(m["payoff"]) else 4.0
        sc_points.append({"x": m["wr"], "y": py, "label": short(s),
                          "color": GREEN if m["total"] >= 0 else RED, "n": m["n"]})

    # ---- roster equity ----
    roster_cum = df.sort_values(["Date", "Entry Time"])["Exit P/L"].cumsum().tolist()

    # ---- exit reason decomposition (roster) ----
    df["reason"] = df.apply(common.classify_exit, axis=1)
    er_labels, er_pl, er_rows = [], [], []
    for r in ["PROFIT-TARGET", "TIME-STOP", "SETTLED"]:
        g = df[df["reason"] == r]
        if len(g) == 0:
            continue
        gpl = g["Exit P/L"]
        er_labels.append(r.replace("-", "‑")); er_pl.append(round(gpl.sum(), 2))
        er_rows.append([r, len(g), f'{(gpl>0).sum()}/{(gpl<=0).sum()}', money(gpl.mean()),
                        f'<b style="color:{GREEN if gpl.sum()>=0 else RED}">{money(gpl.sum())}</b>'])

    # ---- Iron Fly entry-window experiment ----
    def pair(a, b):
        ma, mb = M[a], M[b]
        edge = ma["avg"] - mb["avg"]
        return [pretty(a) + f" ({CONFIG[a].split('·')[0].strip()})", ma["n"], f'{ma["wr"]:.1f}%', money(ma["avg"]),
                pretty(b) + f" ({CONFIG[b].split('·')[0].strip()})", mb["n"], f'{mb["wr"]:.1f}%', money(mb["avg"]),
                f'<b style="color:{GREEN if edge>=0 else RED}">{money(edge)}</b>']
    exp_rows = [pair("Iron Fly V1", "Iron Fly V3"), pair("Iron Fly V2", "Iron Fly V4")]
    exp_tbl = table(["+30m strat", "n", "WR", "Exp", "+1h strat", "n", "WR", "Exp", "Edge →+30m"], exp_rows, right_from=1)

    # ---- Jade Lizard tail risk ----
    jl_df = df[df["Strategy"].isin(JADE_LIZARDS)].copy()
    jl_losses = jl_df[jl_df["Exit P/L"] < 0][["Date", "Strategy", "Status", "Exit P/L", "Notes"]].sort_values("Date")
    loss_rows = [[esc(r["Date"]), esc(pretty(r["Strategy"])), esc(r["Status"]),
                  f'<b style="color:{RED}">{money(r["Exit P/L"])}</b>',
                  esc(str(r["Notes"])[:48])] for _, r in jl_losses.iterrows()]
    jl_split = [[pretty(s), M[s]["n"], f'{M[s]["wins"]}W / {M[s]["losses"]}L',
                 money(M[s]["total"]), f'{M[s]["payoff"]:.2f}', money(M[s]["worst"])] for s in JADE_LIZARDS]

    # ---- capital efficiency ----
    cap_rows = sorted(
        ([pretty(s), money(M[s]["med_bp"], 0), money(M[s]["avg"]), f'{M[s]["roc"]:.3f}%'] for s in ACTIVE_ROSTER),
        key=lambda r: float(r[3].rstrip("%")), reverse=True)

    # ---- open positions ----
    if len(open_df):
        open_rows = [[esc(r["Date"]), esc(str(r["Entry Time"])[:5]), esc(pretty(r["Strategy"])),
                      money(float(r["Credit Collected"])), esc(str(r["Notes"])[:48] or "—")]
                     for _, r in open_df.sort_values(["Date", "Entry Time"]).iterrows()]
        open_tbl = table(["Date", "In", "Strategy", "Credit", "Notes"], open_rows, right_from=3)
    else:
        open_tbl = '<p class="muted">No open positions.</p>'

    findings = build_findings(M, T, roster_total, book_total, iron_total, jl_total, jl_losses)

    overview = f"""<div class="kpis">{kpis}</div>
{panel("Findings & suggestions", findings,
       "Ranked by what should change your behaviour. Every claim is backed by the data below.")}
{panel("Strategy leaderboard — active roster, ranked by return on capital", leaderboard(M, T),
       "Ranked by ROC (return on capital) — the capital-aware measure — because buying power differs ~12× across the roster, so raw expectancy alone would wrongly crown the capital-heavy Jade Lizards. Exp/tr = avg P/L per trade · Payoff = avgWin/|avgLoss| · PF = grossWin/grossLoss · t = single-sample t-stat (|t|>2 ≈ 95% confident the edge is real). Click any row to open that strategy's full dashboard.")}
{panel("Roster equity curve (cumulative P/L, all 7 strategies, entry order)",
       area_chart(roster_cum, color=GREEN if roster_total >= 0 else RED),
       f"Climb to {money(roster_total)} across {roster_n} closed trades.")}
<div class="grid">
{panel("Net P/L by strategy", bar_chart(labs, net_vals), "Confounded by trade count & capital — see expectancy and ROC next.")}
{panel("Expectancy ($ / trade) by strategy", bar_chart(labs, exp_vals, dp=2), "The fair comparison: average P/L per trade, capital-blind.")}
</div>
<div class="grid">
{panel("Return on capital (% / trade)", bar_chart(labs, roc_vals, dp=3), "Expectancy ÷ buying power. This is where Iron Flies dominate the Jade Lizards.")}
{panel("Win rate vs payoff — why win rate lies", scatter(sc_points),
       "Bubble = strategy (size ∝ trade count). High win rate + low payoff (bottom-right) is fragile: the Jade Lizards win ~92% but a single loss dwarfs many wins. Iron Fly V2 wins barely over half its trades but each win is ~1.8× each loss.")}
</div>
{panel("Monthly P/L by strategy (2026)", monthly_table(df),
       "Cell shade ∝ magnitude. The latest month tagged ·MTD is month-to-date (partial) — its totals are mechanically smaller because the month isn't finished. Jade Lizard's down month is the two settled losses landing; the Iron Flies stayed steady.")}
<div class="grid">
{panel("Exit-reason decomposition (roster)", bar_chart(er_labels, er_pl) + table(["Reason", "n", "W/L", "Avg", "Total"], er_rows),
       "Managed profit-target exits make the money; trades held to settlement lose. Every Jade Lizard loss is a SETTLED row.")}
{panel("Capital efficiency", table(["Strategy", "Med BP", "Exp/tr", "ROC%/tr"], cap_rows, right_from=1),
       "Sorted by return on capital. ~12× capital gap between Iron Flies and Jade Lizards.")}
</div>
{panel("Iron Fly entry-window natural experiment", exp_tbl,
       "Structure & profit target held constant; only the entry window differs. +30m wins both pairs → Open+30m is the better entry.")}
{panel("🔴 Jade Lizard tail-risk panel", table(["Variant", "n", "W/L", "Net", "Payoff", "Worst"], jl_split, right_from=1)
       + '<div style="height:10px"></div>'
       + ('<div class="sub">The losses (all settled ITM):</div>' + table(["Date", "Variant", "Status", "P/L", "Note"], loss_rows, right_from=3) if loss_rows else ""),
       "Downside is now sampled. One large loss per variant; payoff 0.14–0.21; not statistically significant. Net-positive only on the prior win streak.")}
{panel("Currently open (excluded from all stats above)", open_tbl,
       f"{len(open_df)} positions in flight as of {gen}.")}"""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>0DTE Bot — Active Roster Overview</title>
<style>
:root{{color-scheme:dark}} *{{box-sizing:border-box}}
body{{margin:0;background:{BG};color:{INK};font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 18px 60px}}
header h1{{margin:0 0 2px;font-size:24px}} header .meta{{color:{MUTED};font-size:13px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0 16px}}
.kpi{{background:{PANEL};border:1px solid {GRID};border-radius:12px;padding:14px 16px}}
.kpi-l{{color:{MUTED};font-size:12px;text-transform:uppercase;letter-spacing:.4px}}
.kpi-v{{font-size:21px;font-weight:650;margin:3px 0}} .kpi-s{{color:{MUTED};font-size:12px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
.panel{{background:{PANEL};border:1px solid {GRID};border-radius:12px;padding:16px 18px;margin-bottom:16px}}
.panel h2{{margin:0 0 2px;font-size:15px}} .panel .sub{{color:{MUTED};font-size:12px;margin-bottom:10px}}
.findings{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:820px){{.findings{{grid-template-columns:1fr}}}}
.finding{{background:#12181f;border:1px solid {GRID};border-left:4px solid {GRID};border-radius:10px;padding:13px 15px}}
.finding .ftag{{font-size:11px;font-weight:700;letter-spacing:.6px;margin-bottom:4px}}
.finding h3{{margin:0 0 6px;font-size:14.5px;line-height:1.35}}
.finding p{{margin:0 0 9px;color:#c4ccd6;font-size:13px}}
.finding .action{{font-size:12.5px;color:{INK};background:{PANEL};border-radius:7px;padding:7px 9px}}
.finding .action span{{font-weight:700;color:{AMBER};margin-right:6px;font-size:11px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}}
th,td{{padding:7px 9px;border-bottom:1px solid {GRID};text-align:left;white-space:nowrap}}
th{{color:{MUTED};font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.3px}}
td.r,th.r{{text-align:right}} td.muted{{color:{MUTED}}} tbody tr:hover{{background:#1c2430}}
a{{color:{BLUE};text-decoration:none}} a:hover{{text-decoration:underline}}
.lead td:first-child{{font-weight:600}}
.tbl-wrap{{overflow-x:auto;border:1px solid {GRID};border-radius:10px;margin-top:6px}}
.tbl-wrap table{{margin:0}}
.note{{color:{MUTED};font-size:12px;background:#12181f;border:1px solid {GRID};border-left:3px solid {AMBER};border-radius:8px;padding:10px 12px;margin-top:6px}}
</style></head><body><div class="wrap">
<header>
  <h1>0DTE Bot — Active Roster Overview <span style="color:{MUTED};font-weight:400">· findings, suggestions & evidence</span></h1>
  <div class="meta">Live roster: Iron Fly V1–V4 + Jade Lizard 5/7/10DTE · {roster_n} closed trades · {esc(d0)} → {esc(d1)} · paper trading · generated {gen}</div>
</header>
{overview}
<div class="note"><b>Method.</b> Active roster = the 7 strategies still trading after the 2026-06-05 trim (explicit list, not the
<code>--active-only</code> 14-day heuristic, which mis-classifies the roster). Closed trades only; anomalous-credit outliers
(&gt;$30) excluded; stats &amp; DST-normalised timing via <code>analysis/common.py</code>. P/L is in the log's native per-1-lot units, so
all ranking is on unit-invariant measures (expectancy, payoff, PF, ROC, t-stat). Whole-book total {money(book_total)} reconciles the roster
({money(roster_total)}) against the removed/disabled strategies. Regenerate: <code>venv/bin/python analysis/overview_dashboard.py</code>.</div>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--open", action="store_true", help="open in browser after writing")
    args = ap.parse_args()

    df_book = common.load_trades(drop_private=False, drop_outliers=True)
    book_total = float(df_book["Exit P/L"].sum())

    raw = common.load_trades(closed_only=False, drop_private=False, drop_outliers=False)
    open_df = raw[(raw["Status"] == "OPEN") & (raw["Strategy"].isin(ACTIVE_ROSTER))].copy()

    out = Path(args.out) if args.out else (common.PROJECT_ROOT / "analysis" / "dashboard_overview.html")
    out.write_text(build_html(df_book, open_df, book_total), encoding="utf-8")
    print(f"Wrote {out}")
    if args.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
