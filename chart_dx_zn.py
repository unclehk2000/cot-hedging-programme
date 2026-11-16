"""COT dealing ranges over 12, 6 and 3 months for the US Dollar Index (DX, ICE 098662) and the 10-Year T-Note (ZN, CBOT 043602):
commercials net % of open interest, quadrants around the CE, and the quadrant ladder. Same design as the index charts.
DX and ZN are context only; they were not part of the hedge backtest. Writes charts/cot_{12,6,3}month_DX_ZN.png."""
import numpy as np, pandas as pd, matplotlib, warnings
warnings.filterwarnings('ignore')
matplotlib.use('Agg')
import matplotlib.pyplot as plt, matplotlib.dates as mdates
import os
import hedge_lib as H
from config import CHART_DIR

BG, FG, MUTED, GRID, BLUE = '#0d0f12', '#e8eaed', '#9aa0a6', '#23272d', '#8ab4f8'
QCOL = {3: '#22b14c', 2: '#7fcf95', 1: '#f08a8a', 0: '#e5262b'}
QHEDGE = {3: 0.0, 2: 1 / 3, 1: 2 / 3, 0: 1.0}
MARKETS = {'DX': ('098662', 'US Dollar Index (DX)'), 'ZN': ('043602', '10-Year T-Note (ZN)')}
comm_pct = H.load_macro_comm


def draw(n, label, fname, tick_months):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9.5, 'text.color': FG, 'axes.labelcolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED})
    fig = plt.figure(figsize=(13.5, 5.6), dpi=200, facecolor=BG)
    outer = fig.add_gridspec(1, 2, left=0.055, right=0.985, top=0.70, bottom=0.21, wspace=0.12)
    rows = []
    for k, (mk, (code, name)) in enumerate(MARKETS.items()):
        x = comm_pct(code).dropna(); w = x.iloc[-n:]; ASOF = x.index[-1]
        hi, lo = w.max(), w.min(); R = hi - lo; ce = (hi + lo) / 2; qs = [lo + i * R / 4 for i in range(5)]
        now = w.iloc[-1]; pos = (now - lo) / R; qn = int(min(np.floor(pos * 4), 3))
        rows.append((mk, round(now, 2), round(pos, 3), qn))
        g = outer[0, k].subgridspec(1, 2, width_ratios=[5.2, 1], wspace=0.03)
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
        below = np.mean(v[:3]) >= ce
        ax.text(edges[0] + pd.Timedelta(days=2), ce + (-0.03 if below else 0.03) * R, 'CE', color='white', fontsize=8.5, ha='left',
                va='top' if below else 'bottom', fontweight='bold', zorder=7)
        ax.scatter([d[-1] + pd.Timedelta(days=3.5)], [now], s=34, color='white', zorder=8)
        ax.set_ylim(lo - 0.08 * R, hi + 0.08 * R); ax.set_xlim(edges[0], edges[-1] + pd.Timedelta(days=2))
        ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=tick_months)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y" if n > 30 else "%d %b"))
        ax.set_title(f'{mk}: commercials {now:+.1f}% of OI, {100 * pos:.0f}% up the range (Q{qn + 1})', loc='left', fontsize=10.5, color=FG, fontweight='bold', pad=8)
        if k == 0: ax.set_ylabel('Net position, % of OI')
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
    fig.text(0.055, 0.925, f'The {label} COT dealing range: Dollar Index and 10-Year Note', fontsize=15, fontweight='bold', color=FG)
    fig.text(0.055, 0.865, f'Commercials net position over the last {n} weeks. The range is split into quadrants around its CE (50%). '
             'The higher the quadrant, the lighter the hedge on a long position:', fontsize=9.5, color=MUTED)
    lx = 0.055
    for qi, lab in ((3, 'Q4 top: 0%'), (2, 'Q3: 33%'), (1, 'Q2: 67%'), (0, 'Q1 bottom: 100%')):
        fig.patches.append(matplotlib.patches.FancyBboxPatch((lx, 0.80), 0.012, 0.028, boxstyle='round,pad=0.002', fc=QCOL[qi], ec='none', transform=fig.transFigure))
        fig.text(lx + 0.017, 0.814, lab, fontsize=9.5, color=FG, va='center'); lx += 0.115
    fig.text(0.055, 0.03, f'Commercials alone, as on the index charts. DX and ZN were not part of the hedge backtest: these show where positioning sits, not a tested rule. '
             f'Bars are drawn from the {label} CE and coloured by quadrant.\n'
             'Source: CFTC Legacy futures-only (US Dollar Index, ICE 098662; 10-Year T-Note, CBOT 043602), % of open interest; '
             f'{n} weeks to {ASOF.day} {ASOF:%b %Y}.', fontsize=8.2, color=MUTED, va='bottom')
    os.makedirs(CHART_DIR, exist_ok=True)
    fig.savefig(f'{CHART_DIR}/{fname}', facecolor=BG); plt.close(fig)
    print(label, rows)


if __name__ == '__main__':
    for n, label, fname, tm in ((52, '12-month', 'cot_12month_DX_ZN.png', 2), (26, '6-month', 'cot_6month_DX_ZN.png', 1),
                                (13, '3-month', 'cot_3month_DX_ZN.png', 1)):
        draw(n, label, fname, tm)
