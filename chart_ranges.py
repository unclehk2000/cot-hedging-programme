"""COT dealing ranges over 12, 6 and 3 months for NQ, ES, RTY and YM: commercials net % of open interest, the range in
quadrants around its CE, and the quadrant hedge ladder. Writes charts/cot_{12,6,3}month_*.png."""
import numpy as np, pandas as pd, matplotlib, warnings
warnings.filterwarnings('ignore')
matplotlib.use('Agg')
import matplotlib.pyplot as plt, matplotlib.dates as mdates
import os
import hedge_lib as H
from config import CHART_DIR

BG, FG, MUTED, GRID, BLUE = '#0d0f12', '#e8eaed', '#9aa0a6', '#23272d', '#8ab4f8'
QCOL = {3: '#22b14c', 2: '#7fcf95', 1: '#f08a8a', 0: '#e5262b'}          # Q4 .. Q1
QHEDGE = {3: 0.0, 2: 1 / 3, 1: 2 / 3, 0: 1.0}
def draw(n, label, fname, tick_months):
    LIVE_H3 = {}
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9.5, 'text.color': FG, 'axes.labelcolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED})
    fig = plt.figure(figsize=(13.5, 8.6), dpi=200, facecolor=BG)
    outer = fig.add_gridspec(2, 2, left=0.055, right=0.985, top=0.80, bottom=0.13, hspace=0.42, wspace=0.12)
    rows = []
    for k, mk in enumerate(('NQ', 'ES', 'RTY', 'YM')):
        c = H.load_cot(mk); x = c.comm_pct.dropna(); w = x.iloc[-n:]; ASOF = x.index[-1]
        cr = H.range_pos(c.comm_pct, n).iloc[-1]; ar = H.range_pos(c.am_pct, n).iloc[-1]; comp = (cr + (1 - ar)) / 2; LIVE_H3[mk] = QHEDGE[int(min(np.floor(comp * 4), 3))]
        hi, lo = w.max(), w.min(); R = hi - lo; ce = (hi + lo) / 2; qs = [lo + i * R / 4 for i in range(5)]
        now = w.iloc[-1]; pos = (now - lo) / R; qn = int(min(np.floor(pos * 4), 3))
        rows.append((mk, now, pos, qn))
        g = outer[k // 2, k % 2].subgridspec(1, 2, width_ratios=[5.2, 1], wspace=0.03)
        ax = fig.add_subplot(g[0]); ax2 = fig.add_subplot(g[1], sharey=ax)
        for a in (ax, ax2):
            a.set_facecolor(BG)
            for sp in a.spines.values(): sp.set_visible(False)
        d = w.index; v = w.values; edges = list(d) + [d[-1] + pd.Timedelta(days=7)]
        for i in range(len(v)):
            qi = int(min(np.floor((v[i] - lo) / R * 4), 3))
            ax.fill_between([edges[i], edges[i + 1]], ce, v[i], color=QCOL[qi], alpha=0.95, lw=0)
        for i, yv in enumerate(qs):
            if i == 2: ax.axhline(yv, color='white', lw=2.0, zorder=5)
            else: ax.axhline(yv, color=BLUE if i in (1, 3) else MUTED, lw=0.9, ls=(0, (1, 2)) if i in (1, 3) else (0, (4, 3)), zorder=4)
        below = np.mean(v[:3]) >= ce      # label the CE on the empty side of the first bars
        ax.text(edges[0] + pd.Timedelta(days=2), ce + (-0.03 if below else 0.03) * R, 'CE', color='white', fontsize=8.5, ha='left',
                va='top' if below else 'bottom', fontweight='bold', zorder=7)
        ax.scatter([d[-1] + pd.Timedelta(days=3.5)], [now], s=34, color='white', zorder=8)
        ax.set_ylim(lo - 0.08 * R, hi + 0.08 * R); ax.set_xlim(edges[0], edges[-1] + pd.Timedelta(days=2))
        ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=tick_months)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y" if n > 30 else "%d %b"))
        ax.set_title(f'{mk}: commercials {now:+.1f}% of OI, {100 * pos:.0f}% up the range (Q{qn + 1})', loc='left', fontsize=10.5, color=FG, fontweight='bold', pad=8)
        if k % 2 == 0: ax.set_ylabel('Net position, % of OI')
        # H3 strip
        for i in range(4):
            ax2.fill_between([-0.5, 0.5], qs[i], qs[i + 1], color=QCOL[i], alpha=0.55, lw=0)
            yc = (qs[i] + qs[i + 1]) / 2
            if abs(yc - now) > 0.12 * R:
                ax2.text(0, yc, f'Q{i + 1} · {100 * QHEDGE[i]:.0f}%', ha='center', va='center', color='white', fontsize=8.2)
        ax2.axhline(ce, color='white', lw=1.4, xmin=0.05, xmax=0.95)
        ax2.text(0, now, f' Q{qn + 1} · {100 * QHEDGE[qn]:.0f}% ', ha='center', va='center', color=BG, fontsize=9.5, fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none'), zorder=10)
        ax2.text(0, hi + 0.08 * R, 'Quadrant\nhedge', ha='center', va='bottom', color=FG, fontsize=8.5, fontweight='bold')
        ax2.set_xlim(-0.6, 0.6); ax2.set_xticks([]); ax2.tick_params(axis='y', left=False, labelleft=False)
    fig.text(0.055, 0.945, f'The {label} COT dealing range: four quadrants, four hedge sizes', fontsize=15, fontweight='bold', color=FG)
    fig.text(0.055, 0.905, f'Commercials net position over the last {n} weeks. The range is split into quadrants around its CE (50%). '
             'The higher the quadrant, the lighter the hedge:', fontsize=9.5, color=MUTED)
    lx = 0.055
    for qi, lab in ((3, 'Q4 top: 0%'), (2, 'Q3: 33%'), (1, 'Q2: 67%'), (0, 'Q1 bottom: 100%')):
        fig.patches.append(matplotlib.patches.FancyBboxPatch((lx, 0.866), 0.012, 0.018, boxstyle='round,pad=0.002', fc=QCOL[qi], ec='none', transform=fig.transFigure))
        fig.text(lx + 0.017, 0.875, lab, fontsize=9.5, color=FG, va='center'); lx += 0.115
    fig.text(0.055, 0.03, 'Shown on commercials alone. With the asset-manager reading folded in (flipped), the same quadrant ladder gives '
             f'{100 * LIVE_H3["NQ"]:.0f}% NQ, {100 * LIVE_H3["ES"]:.0f}% ES, {100 * LIVE_H3["RTY"]:.0f}% RTY, {100 * LIVE_H3["YM"]:.0f}% YM this week.\n' + NOTE[n] +
             f' Bars are drawn from the {label} CE and coloured by quadrant.\n'
             'Source: CFTC Legacy futures-only (NQ 209742, ES 13874A, RTY 239742, YM 124603), '
             f'% of open interest; {n} weeks to {ASOF.day} {ASOF:%b %Y}.', fontsize=8.2, color=MUTED, va='bottom')
    os.makedirs(CHART_DIR, exist_ok=True)
    fig.savefig(f'{CHART_DIR}/{fname}', facecolor=BG); plt.close(fig)
    for r in rows: print(r)
    print(LIVE_H3)


NOTE = {52: 'Backtested 12-month rule is the CE split (H2: 25% / 75%); quadrants on 12 months are untested.',
        26: 'This is H3, the tested 6-month rule.',
        13: 'Quadrants on 3 months are untested: an illustration, not a backtested rule.'}
if __name__ == '__main__':
    for n, label, fname, tm in ((52, '12-month', 'cot_12month_quadrants.png', 2), (26, '6-month', 'cot_6month_quadrants.png', 1),
                                (13, '3-month', 'cot_3month_quadrants.png', 1)):
        draw(n, label, fname, tm)
