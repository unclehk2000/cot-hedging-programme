"""Drawdowns of the combined book (25% in each of NQ, ES, RTY, YM): unhedged, static 50% and the H1 COT hedge.
Reads results/book4_drawdowns_weekly.csv (written by run_backtest.py). Writes charts/book4_drawdowns.png."""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from config import RESULTS_DIR, CHART_DIR

BG, FG, MUTED, GRID = '#0d0f12', '#e8eaed', '#9aa0a6', '#23272d'
SERIES = {'Unhedged': '#9aa0a6', 'Static 50%': '#8ab4f8', 'H1 Percentile': '#fbbc04'}

d = pd.read_csv(f'{RESULTS_DIR}/book4_drawdowns_weekly.csv', index_col=0, parse_dates=True).dropna()
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9.5, 'text.color': FG, 'axes.labelcolor': MUTED,
                     'xtick.color': MUTED, 'ytick.color': MUTED})
fig, ax = plt.subplots(figsize=(13.5, 5.6), dpi=200, facecolor=BG)
fig.subplots_adjust(left=0.06, right=0.985, top=0.80, bottom=0.14)
ax.set_facecolor(BG)
for sp in ax.spines.values():
    sp.set_visible(False)
test0 = pd.Timestamp('2021-01-01')
for name, col in SERIES.items():
    ax.plot(d.index, d[name], color=col, lw=1.6 if name != 'Unhedged' else 1.2,
            label=f'{name}: worst {d[name].min():.1f}% overall, {d.loc[test0:, name].min():.1f}% in the test window')
ax.axvline(test0, color=MUTED, lw=0.8, ls=(0, (4, 3)))
ax.text(test0 + pd.Timedelta(days=20), d.min().min() * 0.97, 'Locked test window from here', color=MUTED, fontsize=8.5, va='bottom')
ax.axhline(0, color=GRID, lw=0.8)
ax.yaxis.grid(True, color=GRID, lw=0.6)
ax.set_axisbelow(True)
ax.set_ylabel('Drawdown from peak, %')
ax.legend(loc='lower left', frameon=False, labelcolor=FG, fontsize=9)
fig.text(0.06, 0.92, 'Four index books combined: drawdowns, unhedged vs static 50% vs the COT hedge (H1)', fontsize=14, fontweight='bold', color=FG)
fig.text(0.06, 0.865, 'Equal notional in NQ, ES, RTY and YM, each hedged with its own contract; weekly closes, costs included.',
         fontsize=9.5, color=MUTED)
fig.text(0.06, 0.03, f'Source: run_backtest.py; CFTC COT, futures prices to {d.index[-1]:%d %b %Y}. YM, and so the combined book, starts Sep 2017.',
         fontsize=8.2, color=MUTED)
os.makedirs(CHART_DIR, exist_ok=True)
fig.savefig(f'{CHART_DIR}/book4_drawdowns.png', facecolor=BG)
plt.close(fig)
print('ok')
