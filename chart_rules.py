"""How the four hedge rules read the COT dealing range: NQ commercials over the last 52 weeks, with the 6-month quadrants
and the hedge each rule gives at every level. Writes charts/cot_rules_explainer.png."""
import numpy as np, pandas as pd, matplotlib, warnings
warnings.filterwarnings('ignore')
matplotlib.use('Agg')
import matplotlib.pyplot as plt, matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap
import os
import hedge_lib as H
from config import CHART_DIR

c = H.load_cot('NQ'); x = c.comm_pct.dropna(); ASOF = x.index[-1]; DATE = f'{ASOF.day} {ASOF:%b %Y}'
S = H.signals(c).iloc[[-1]]; LIVE = [float(np.asarray(f(S))[0]) for f in (H.h_percentile, H.h_ce, H.h_quadrant, H.h_ce_quad)]
last52 = x.iloc[-52:]; last26 = x.iloc[-26:]
hi12, lo12 = last52.max(), last52.min(); ce = (hi12 + lo12) / 2
hi6, lo6 = last26.max(), last26.min(); q = [lo6 + k * (hi6 - lo6) / 4 for k in range(5)]
now = x.iloc[-1]; r52 = (now - lo12) / (hi12 - lo12)
def quad(v): return int(min(np.floor(np.clip((v - lo6) / (hi6 - lo6), 0, 1) * 4), 3))
def h1(v): return 1 - np.clip((np.sum(last52.values <= v) - 1) / 51, 0, 1)
def h2(v): return 0.25 if v >= ce else 0.75
def h3(v): return [1.0, 2 / 3, 1 / 3, 0.0][quad(v)]
def h4(v): return [0.5, 0.5, 0.25, 0.0][quad(v)] if v >= ce else [1.0, 0.75, 0.5, 0.5][quad(v)]

BG, FG, MUTED, GRID = '#0d0f12', '#e8eaed', '#9aa0a6', '#23272d'
GREEN, RED, BLUE = '#22b14c', '#e5262b', '#8ab4f8'
cmap = LinearSegmentedColormap.from_list('h', ['#1f9d47', '#30353b', '#d23a3a'])
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'text.color': FG, 'axes.labelcolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED})
fig = plt.figure(figsize=(13.5, 7.4), dpi=200, facecolor=BG)
gs = fig.add_gridspec(1, 2, width_ratios=[3.1, 1.55], wspace=0.04, left=0.06, right=0.985, top=0.80, bottom=0.14)
ax = fig.add_subplot(gs[0]); ax2 = fig.add_subplot(gs[1], sharey=ax)
for a in (ax, ax2):
    a.set_facecolor(BG)
    for s in a.spines.values(): s.set_visible(False)
R = hi12 - lo12; pad = 0.07 * R; ylo, yhi = lo12 - pad, hi12 + pad
d = last52.index; v = last52.values; edges = list(d) + [d[-1] + pd.Timedelta(days=7)]
for i in range(len(v)):
    up = v[i] >= ce
    ax.fill_between([edges[i], edges[i + 1]], ce, v[i], color=GREEN if up else RED, alpha=0.95, lw=0)
    ax.plot([edges[i], edges[i + 1]], [v[i], v[i]], color='#7ee29a' if up else '#ff6b6b', lw=0.8)
ax.axhline(ce, color='white', lw=2.2, zorder=5)
ax.axhline(hi12, color=MUTED, lw=0.9, ls=(0, (4, 3)), zorder=4); ax.axhline(lo12, color=MUTED, lw=0.9, ls=(0, (4, 3)), zorder=4)
ax.text(edges[0], hi12 + 0.012 * R, f'12-month high  {hi12:+.1f}%', color=MUTED, fontsize=8.5, va='bottom')
ax.text(d[2], lo12 - 0.012 * R, f'12-month low  {lo12:+.1f}%', color=MUTED, fontsize=8.5, va='top')
ax.text(edges[0], ce + 0.015 * R, 'CE: 50% of the 12-month range', color='white', fontsize=9, va='bottom', fontweight='bold', zorder=6)
x6 = edges[-27]
for k, yv in enumerate(q):
    ax.plot([x6, edges[-1]], [yv, yv], color=BLUE, lw=1.0 if k in (0, 4) else 0.8, ls=(0, (1, 2)), zorder=4)
for k, lab in enumerate(['Q1', 'Q2', 'Q3', 'Q4']):
    ax.text(edges[-1] - pd.Timedelta(days=3), (q[k] + q[k + 1]) / 2, lab, color=BLUE, fontsize=9, ha='right', va='center', zorder=6)
ax.axvline(x6, color=BLUE, lw=0.6, alpha=0.5, ls=(0, (1, 2)))
ax.annotate('6-month range in quadrants', xy=(x6, q[4]), xytext=(x6 - pd.Timedelta(days=60), q[4] + 0.07 * R), color=BLUE, fontsize=8.5,
            arrowprops=dict(arrowstyle='-', color=BLUE, lw=0.7))
ax.text(d[1], ce + 0.42 * R, 'Premium (above CE)\ncommercials buying\n= lighter hedge', color=GREEN, fontsize=9.5, fontweight='bold', va='center')
ax.text(d[23], ce - 0.16 * R, 'Discount (below CE)\ncommercials selling\n= heavier hedge', color=RED, fontsize=9.5, fontweight='bold', va='center')
ax.scatter([d[-1] + pd.Timedelta(days=3.5)], [now], s=42, color='white', zorder=8)
QNAME = ['Q1, the bottom', 'Q2, the lower middle', 'Q3, the upper middle', 'Q4, the top'][quad(now)]
ax.annotate(f'This week ({ASOF.day} {ASOF:%b}): {now:+.1f}% of OI\n{100 * r52:.0f}% up the 12-month range: {"above" if now >= ce else "below"} CE\n{QNAME} of the 6-month range',
            xy=(d[-1] + pd.Timedelta(days=3.5), now), xytext=(d[23], lo12 + 0.16 * R), color=FG, fontsize=8.5, va='center',
            arrowprops=dict(arrowstyle='-', color=FG, lw=0.7), zorder=9)
ax.set_ylim(ylo, yhi); ax.set_xlim(edges[0], edges[-1] + pd.Timedelta(days=2))
ax.set_ylabel('Commercials net position, % of open interest'); ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[12, 2, 4, 6, 8, 10])); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
cols = [('H1', 'ladder', h1), ('H2', '12-month\nCE', h2), ('H3', '6-month\nquadrants', h3), ('H4', 'CE +\nquadrant', h4)]
ys = np.linspace(ylo, yhi, 700); w = 0.78
for j, (code, name, f) in enumerate(cols):
    vals = np.array([f(y) for y in ys]); vals = np.where((ys < lo12) | (ys > hi12), np.nan, vals)
    ax2.imshow(np.ma.masked_invalid(vals[:, None]), extent=(j - w / 2, j + w / 2, ylo, yhi), origin='lower', aspect='auto',
               cmap=cmap, vmin=0, vmax=1, alpha=0.95, interpolation='nearest')
    if code != 'H1':
        segs, start = [], 0
        for i in range(1, len(ys) + 1):
            if i == len(ys) or np.isnan(vals[i]) != np.isnan(vals[start]) or (not np.isnan(vals[i]) and vals[i] != vals[start]):
                if not np.isnan(vals[start]): segs.append((ys[start], ys[i - 1], vals[start]))
                start = i
        for a0, a1, hv in segs:
            yc = (a0 + a1) / 2
            if a0 <= now <= a1: yc = a1 - 0.04 * R
            if (a1 - a0) > 0.035 * R and abs(yc - now) > 0.035 * R and abs(yc - ce) > 0.03 * R:
                ax2.text(j, yc, f'{100 * hv:.0f}%', ha='center', va='center', color='white', fontsize=9, alpha=0.9)
    else:
        for yy in (hi12 - 0.05 * R, ce + 0.06 * R, ce - 0.12 * R):
            ax2.text(j, yy, f'{100 * f(yy):.0f}%', ha='center', va='center', color='white', fontsize=8.5, alpha=0.9)
    ax2.text(j, yhi + 0.015 * R, f'{code}\n{name}', ha='center', va='bottom', color=FG, fontsize=9, fontweight='bold', linespacing=1.15)
    ax2.text(j, now, f' {100 * f(now):.0f}% ', ha='center', va='center', color=BG, fontsize=10, fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='none'), zorder=10)
ax2.axhline(now, color='white', lw=1.0, ls=(0, (3, 2)), zorder=9); ax2.axhline(ce, color='white', lw=1.6, zorder=8, alpha=0.8)
ax2.set_xlim(-0.55, 3.55); ax2.set_xticks([]); ax2.tick_params(axis='y', left=False, labelleft=False)
fig.text(0.06, 0.945, 'How the four hedge rules read the COT dealing range', fontsize=15, fontweight='bold', color=FG)
fig.text(0.06, 0.905, 'NQ commercials, last 12 months. Above the CE = buying = lighter hedge; below = selling = heavier hedge.', fontsize=9.5, color=MUTED)
fig.text(0.06, 0.875, "Each column on the right turns that level into a hedge. This week's level is the white dashed line.", fontsize=9.5, color=MUTED)
fig.text(0.06, 0.04, 'Shown on commercials alone. The programme averages this with the asset-manager reading flipped, which gives NQ '
         f'{" / ".join(f"{100 * v:.0f}%" for v in LIVE)} this week.\nH1 uses rank in the last 52 weeks rather than distance in the range. '
         f'Source: CFTC Legacy futures-only, NQ 209742, % of open interest; 52 weeks to {DATE}.', fontsize=8.3, color=MUTED, va='bottom')
os.makedirs(CHART_DIR, exist_ok=True)
fig.savefig(f'{CHART_DIR}/cot_rules_explainer.png', facecolor=BG); plt.close(fig)
print('ok')
