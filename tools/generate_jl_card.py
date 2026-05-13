"""Generate a bot-style trade signal card for a Jade Lizard position."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import numpy as np

# ── Trade data ────────────────────────────────────────────────────────────────
SPOT          = 7325.18
SHORT_PUT     = 7255
LONG_PUT      = 7235
SHORT_CALL    = 7395
LONG_CALL     = 7400
CREDIT        = 4.60
PROFIT_TARGET = 1.15
BUYING_POWER  = 1540.00
EXPIRY        = "11 May 2026"
DTE           = 5
EM            = 71.57
ENTRY_TIME    = "15:30 BST"
ENTRY_DATE    = "06 May 2026"
PUT_WIDTH     = SHORT_PUT - LONG_PUT    # 20
CALL_WIDTH    = LONG_CALL - SHORT_CALL  # 5

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#0B0E14"
CARD    = "#131720"
BORDER  = "#1E2535"
ORANGE  = "#F07B2F"
GREEN   = "#27AE60"
RED     = "#C0392B"
BLUE    = "#4A90D9"
WHITE   = "#E8ECF2"
MUTED   = "#5A6580"
DIM     = "#2A3045"

fig = plt.figure(figsize=(9, 5), facecolor=BG)

# ── Outer border card ─────────────────────────────────────────────────────────
outer = FancyBboxPatch((0.02, 0.02), 0.96, 0.96,
                        boxstyle="round,pad=0.01",
                        linewidth=1.5, edgecolor=BORDER,
                        facecolor=CARD, transform=fig.transFigure,
                        zorder=0, clip_on=False)
fig.add_artist(outer)

# ── Orange left accent bar ────────────────────────────────────────────────────
fig.add_artist(plt.Rectangle((0.02, 0.02), 0.005, 0.96,
               transform=fig.transFigure, color=ORANGE, zorder=1, clip_on=False))

def T(x, y, s, size=10, color=WHITE, weight='normal', ha='left', va='center', alpha=1.0, style='normal'):
    fig.text(x, y, s, fontsize=size, color=color, fontweight=weight,
             ha=ha, va=va, fontfamily='sans-serif', alpha=alpha, style=style)

# ── Header ────────────────────────────────────────────────────────────────────
T(0.07, 0.88, "JADE LIZARD", size=18, color=ORANGE, weight='bold')
T(0.07, 0.78, "SPX", size=13, color=WHITE, weight='bold')
T(0.14, 0.78, "· 5DTE ·", size=11, color=MUTED)
T(0.22, 0.78, f"Exp {EXPIRY}", size=11, color=WHITE)

# Timestamp right-aligned
T(0.93, 0.88, f"⚡ BOT ENTRY", size=8, color=ORANGE, weight='bold', ha='right')
T(0.93, 0.80, f"{ENTRY_DATE}  {ENTRY_TIME}", size=8, color=MUTED, ha='right')

# ── Horizontal rule ───────────────────────────────────────────────────────────
fig.add_artist(plt.Line2D([0.07, 0.93], [0.71, 0.71],
               transform=fig.transFigure, color=BORDER, linewidth=1))

# ── Strike ladder (centre visual) ────────────────────────────────────────────
# Draw a simple horizontal price ladder showing the 4 strikes around spot
# Layout: LP ----[PUT SPREAD]---- SP ....SPOT.... SC --[CALL SPREAD]-- LC

ax = fig.add_axes([0.07, 0.38, 0.86, 0.25], facecolor='none')
ax.set_xlim(LONG_PUT - 30, LONG_CALL + 30)
ax.set_ylim(-1, 1)
ax.axis('off')

# Put spread zone (red fill)
ax.fill_betweenx([-0.18, 0.18], LONG_PUT, SHORT_PUT,
                  color=RED, alpha=0.25)
ax.plot([LONG_PUT, SHORT_PUT], [0, 0], color=RED, linewidth=3, solid_capstyle='butt')

# Profit zone (green fill)
ax.fill_betweenx([-0.18, 0.18], SHORT_PUT, SHORT_CALL,
                  color=GREEN, alpha=0.15)
ax.plot([SHORT_PUT, SHORT_CALL], [0, 0], color=GREEN, linewidth=3, solid_capstyle='butt')

# Call spread zone (small, orange)
ax.fill_betweenx([-0.18, 0.18], SHORT_CALL, LONG_CALL,
                  color=ORANGE, alpha=0.25)
ax.plot([SHORT_CALL, LONG_CALL], [0, 0], color=ORANGE, linewidth=3, solid_capstyle='butt')

# Strike tick marks and labels
for strike, label, color, yoff in [
    (LONG_PUT,   f"{LONG_PUT}",   MUTED,  0.38),
    (SHORT_PUT,  f"{SHORT_PUT}",  RED,    0.38),
    (SHORT_CALL, f"{SHORT_CALL}", GREEN,  0.38),
    (LONG_CALL,  f"{LONG_CALL}",  ORANGE, 0.38),
]:
    ax.plot([strike, strike], [-0.22, 0.22], color=color, linewidth=1.2, alpha=0.8)
    ax.text(strike, yoff, label, ha='center', va='bottom',
            fontsize=8.5, color=color, fontfamily='monospace', fontweight='bold')

# Spot marker
ax.axvline(SPOT, color=WHITE, linewidth=1.5, linestyle='--', alpha=0.6, zorder=5)
ax.text(SPOT, -0.55, f"SPX {SPOT:.0f}", ha='center', va='top',
        fontsize=8, color=WHITE, alpha=0.85, fontfamily='monospace')

# Zone labels below the bar
ax.text((LONG_PUT + SHORT_PUT) / 2, -0.28, "PUT SPREAD",
        ha='center', va='top', fontsize=6.5, color=RED, alpha=0.8)
ax.text((SHORT_PUT + SHORT_CALL) / 2, -0.28, "MAX PROFIT ZONE",
        ha='center', va='top', fontsize=6.5, color=GREEN, alpha=0.8)
ax.text((SHORT_CALL + LONG_CALL) / 2, -0.28, "CALL",
        ha='center', va='top', fontsize=6.5, color=ORANGE, alpha=0.8)

# EM bracket
em_y = 0.72
ax.annotate('', xy=(SPOT + EM, em_y), xytext=(SPOT, em_y),
            arrowprops=dict(arrowstyle='->', color=BLUE, lw=1.0))
ax.annotate('', xy=(SPOT - EM, em_y), xytext=(SPOT, em_y),
            arrowprops=dict(arrowstyle='->', color=BLUE, lw=1.0))
ax.text(SPOT, em_y + 0.08, f"±EM  {EM:.0f} pts",
        ha='center', va='bottom', fontsize=7, color=BLUE, alpha=0.8)

# ── Horizontal rule ───────────────────────────────────────────────────────────
fig.add_artist(plt.Line2D([0.07, 0.93], [0.35, 0.35],
               transform=fig.transFigure, color=BORDER, linewidth=1))

# ── Stats row ─────────────────────────────────────────────────────────────────
stats = [
    ("CREDIT",        f"${CREDIT:.2f}",              GREEN),
    ("PROFIT TARGET", f"${PROFIT_TARGET:.2f}  (25%)", GREEN),
    ("BUYING POWER",  f"${BUYING_POWER:,.0f}",        WHITE),
    ("PUT SPREAD",    f"{SHORT_PUT}/{LONG_PUT}  20pt", RED),
    ("CALL SPREAD",   f"{SHORT_CALL}/{LONG_CALL}  5pt",ORANGE),
]

n = len(stats)
for i, (label, value, clr) in enumerate(stats):
    x = 0.07 + i * (0.86 / n) + (0.86 / n) * 0.02
    cx = x + (0.86 / n) * 0.46
    T(cx, 0.27, label, size=6.5, color=MUTED, ha='center', weight='bold')
    T(cx, 0.19, value, size=9,   color=clr,   ha='center', weight='bold')

# ── Footer ────────────────────────────────────────────────────────────────────
fig.add_artist(plt.Line2D([0.07, 0.93], [0.12, 0.12],
               transform=fig.transFigure, color=BORDER, linewidth=0.6))

T(0.07, 0.07, "#SPX  #JadeLizard  #0DTE  #OptionsTrading",
  size=7, color=MUTED, alpha=0.7, style='italic')
T(0.93, 0.07, "paper trading", size=7, color=MUTED, ha='right', alpha=0.6)

plt.savefig("jl_trade_card.png", dpi=200, bbox_inches='tight',
            facecolor=BG, edgecolor='none')
print("Saved: jl_trade_card.png")
