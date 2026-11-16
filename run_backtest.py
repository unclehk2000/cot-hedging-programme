"""Four-market backtest: NQ, ES, RTY and YM books, each hedged with its own futures contract and sized off its own COT
(asset managers from TFF, commercials from Legacy). The orientation was set in the NQ fit window (commercials high =
bullish, asset managers high = bearish) and applied unchanged to ES, RTY and YM.
Fit window to 2020, locked test window 2021 onwards. Needs the price files described in data/prices/README.md.

Writes results/backtest_results.json, results/rolls_<MK>.csv, results/book4_drawdowns_weekly.csv and
results/h1_ratio_weekly_4markets.csv."""
import json, os, warnings, numpy as np, pandas as pd
import hedge_lib as H
from config import RESULTS_DIR, MARKETS
warnings.filterwarnings('ignore')
OUT = RESULTS_DIR; os.makedirs(OUT, exist_ok=True)
FIT_END = pd.Timestamp('2020-12-31'); TEST0 = pd.Timestamp('2021-01-01')
RULES = {'Unhedged': lambda s: np.zeros(len(s)), 'Static 50%': lambda s: np.full(len(s), 0.5),
         'H1 Percentile': H.h_percentile, 'H2 12m CE': H.h_ce, 'H3 6m quadrants': H.h_quadrant, 'H4 CE + quadrant': H.h_ce_quad}


def schedule(sig, hw, idx):
    hw = pd.Series(np.asarray(hw, float), index=sig.index)
    hw = hw[sig.index >= pd.Timestamp('2014-06-01')].dropna()
    exe = []
    for asof in hw.index:
        j = idx.searchsorted(sig.loc[asof, 'release'], side='right')
        exe.append(idx[j] if j < len(idx) else pd.NaT)
    e = pd.DataFrame({'h': hw.values, 'exe': exe, 'asof': hw.index}).dropna(subset=['exe']).groupby('exe').last()
    hc = pd.Series(np.nan, index=idx); hc.loc[e.index] = e['h'].values; hc = hc.ffill()
    a = pd.Series(pd.NaT, index=idx, dtype='datetime64[ns]'); a.loc[e.index] = e['asof'].values; a = a.ffill()
    return hc, a, e.index


def simulate(px, hc, td, mk, start, book=10.0):
    F = px.AdjClose - px.off; mult = H.MULT[mk]; tick = H.TICK[mk]; con = px.Contract
    book_not = book * mult * F
    pos = pd.Series(np.nan, index=px.index); m = px.index.isin(td); pos[m] = (hc * book)[m]; pos = pos.ffill().fillna(0.0)
    roll_close = (con != con.shift(-1)) & con.shift(-1).notna()
    d = pd.DataFrame(index=px.index)
    d['r_book'] = px.ret
    d['r_hedge'] = -pos.shift(1) * px.dpts * mult / book_not.shift(1)
    d['cost_rebal'] = pos.diff().abs().fillna(pos.abs()) * (tick + H.FEE) / book_not
    d['cost_roll'] = pos.abs() * (tick + 2 * H.FEE) * roll_close / book_not
    d['r'] = d.r_book + d.r_hedge - d.cost_rebal - d.cost_roll
    d['h_eff'] = pos / book
    d['im'] = pos.abs() * H.margin_ratio(mk) * F * mult / book_not
    d['roll_close'] = roll_close; d['pos'] = pos
    return d.loc[start:]


def pstats(d, lo=None, hi=None):
    x = d.loc[lo:hi]; st = H.stats(x)
    yrs = (x.index[-1] - x.index[0]).days / 365.25
    st.update(avg_h=100 * x.h_eff.mean(), cost_bp_yr=1e4 * (x.cost_rebal.sum() + x.cost_roll.sum()) / yrs,
              roll_cost_bp_yr=1e4 * x.cost_roll.sum() / yrs, avg_im=100 * x.im.mean(),
              vm_worst_21d=100 * x.r_hedge.fillna(0).rolling(21).sum().min(), vm_worst_63d=100 * x.r_hedge.fillna(0).rolling(63).sum().min(),
              start=str(x.index[0].date()), end=str(x.index[-1].date()))
    return st


def weekly(d, a):
    w = pd.DataFrame({'r_book': d.r_book, 'r': d.r, 'h': d.h_eff, 'asof': a.shift(1).reindex(d.index)}).dropna(subset=['asof'])
    g = w.groupby('asof')
    return pd.DataFrame({'r_book': g.r_book.apply(lambda x: (1 + x).prod() - 1), 'r': g.r.apply(lambda x: (1 + x).prod() - 1), 'h': g.h.mean()})


def wk_metrics(rw):
    e = (1 + rw).cumprod(); mdd = (e / e.cummax() - 1).min(); yrs = len(rw) / 52.18
    return (e.iloc[-1] ** (1 / yrs) - 1) / abs(mdd), mdd


RES, REG, NULL, SIT, CARRY, ROLLS, DAILY, EPS = {}, {}, {}, {}, {}, {}, {}, {}
for mk in MARKETS:
    px = H.load_px(mk)
    start = max(pd.Timestamp('2015-01-02'), px.index[0] + pd.Timedelta(days=5))
    px = px.loc[start - pd.Timedelta(days=10):]
    c = H.load_cot(mk); s = H.signals(c)
    sig = {'composite': s, 'comm': H.signals(c, ('comm',)), 'am': H.signals(c, ('am',))}
    # ---- situation analysis: each driver vs next-13-week book return, fit and test
    eq = (1 + px.ret.fillna(0)).cumprod(); idx = px.index; rows = []
    for asof, r in s.iterrows():
        j = idx.searchsorted(r.release, side='right')
        if j + 65 >= len(idx) or idx[j] < start: continue
        path = eq.iloc[j:j + 66] / eq.iloc[j]
        rows.append(dict(asof=asof, f13=path.iloc[-1] - 1, mdd13=(path / path.cummax() - 1).min()))
    F = pd.DataFrame(rows).set_index('asof'); X = s.join(F, how='inner')
    SIT[mk] = dict(corr_am_comm=float(c.am_pct.corr(c.comm_pct)), corr_comm_dealer=float(c.comm_pct.corr(100 * c.dealer_net / c.oi)),
                   am_now=float(c.am_pct.iloc[-1]), comm_now=float(c.comm_pct.iloc[-1]))
    for per, m in (('fit', X.index <= FIT_END), ('test', X.index > FIT_END)):
        Y = X[m]
        SIT[mk][per] = {k: dict(rho_f13=float(Y[k].corr(Y.f13, method='spearman')), n=int(len(Y)),
                                f13_above=100 * float(Y[Y[k.replace('p52', 'r52')] >= 0.5].f13.mean()),
                                f13_below=100 * float(Y[Y[k.replace('p52', 'r52')] < 0.5].f13.mean()))
                        for k in ('comm_pct_p52', 'am_pct_p52', 'p52')}
    # ---- strategies
    RES[mk] = {}; W = {}
    for name, f in RULES.items():
        hc, a, td = schedule(s, f(s), px.index); d = simulate(px, hc, td, mk, start)
        DAILY[f'{name} | {mk}'] = d; W[name] = weekly(d, a)
        RES[mk][name] = {p: pstats(d, lo, hi) for p, lo, hi in (('full', None, None), ('fit', None, FIT_END), ('test', TEST0, None))}
    for src in ('comm', 'am'):
        for name, f in (('H1 Percentile', H.h_percentile), ('H2 12m CE', H.h_ce)):
            sg = sig[src]; hc, a, td = schedule(sg, f(sg), px.index); d = simulate(px, hc, td, mk, start)
            RES[mk][f'{name} · {src} only'] = {p: pstats(d, lo, hi) for p, lo, hi in (('fit', None, FIT_END), ('test', TEST0, None))}
    # ---- null: circular shifts of the weekly hedge path, test window
    NULL[mk] = {}
    for name in ('H1 Percentile', 'H2 12m CE', 'H3 6m quadrants', 'H4 CE + quadrant'):
        w = W[name]; ww = w[w.index > FIT_END]; r = ww.r_book.values; h = ww.h.values
        act, act_mdd = wk_metrics(pd.Series((1 - h) * r))
        sh = [wk_metrics(pd.Series((1 - np.roll(h, k)) * r)) for k in range(26, len(r) - 26)]
        cals = np.array([x[0] for x in sh]); mdds = np.array([x[1] for x in sh])
        NULL[mk][name] = dict(p_calmar=float((cals >= act).mean()), p_mdd=float((mdds >= act_mdd).mean()), shifts=len(sh))
    # ---- hit rate by regime (H1, vs static), fit and test
    w = W['H1 Percentile'].join(s[['r52', 'r26']], how='left'); w['ex'] = w.r - W['Static 50%'].r.reindex(w.index); w['tilt'] = w.h - 0.5
    w['side'] = np.where(w.r52 >= 0.5, 'Premium (above 12m CE)', 'Discount (below 12m CE)')
    w['quad'] = np.minimum(np.floor(w.r26 * 4), 3).map({3: 'Q4 top', 2: 'Q3', 1: 'Q2', 0: 'Q1 bottom'})
    rows = []
    for per, m in (('fit', w.index <= FIT_END), ('test', w.index > FIT_END)):
        for col in ('side', 'quad'):
            for g, x in w[m].groupby(col):
                t = x[x.tilt.abs() > 1e-9]; k = int(((t.tilt * t.r_book) < 0).sum()); n = len(t); lo, hi = H.wilson(k, n)
                rows.append(dict(period=per, type=col, regime=g, weeks=len(x), avg_h=100 * x.h.mean(), up_share=100 * (x.r_book > 0).mean(),
                                 hit=100 * k / n if n else np.nan, lo=100 * lo, hi=100 * hi, ex_bp=1e4 * x.ex.mean(), t=H.nw_t(x.ex.values) if len(x) > 10 else np.nan))
        t = w[m][w[m].tilt.abs() > 1e-9]; k = int(((t.tilt * t.r_book) < 0).sum()); n = len(t)
        rows.append(dict(period=per, type='all', regime='All weeks', weeks=int(m.sum()), avg_h=100 * w[m].h.mean(), up_share=100 * (w[m].r_book > 0).mean(),
                         hit=100 * k / n, lo=100 * H.wilson(k, n)[0], hi=100 * H.wilson(k, n)[1], ex_bp=1e4 * w[m].ex.mean(), t=H.nw_t(w[m].ex.values)))
    REG[mk] = rows
    # ---- rolls and carry
    R = H.rolls(px, mk); R = R[R.date >= start]; ROLLS[mk] = R; R.to_csv(f'{OUT}/rolls_{mk}.csv', index=False)
    CARRY[mk] = {}
    for name in ('Static 50%', 'H1 Percentile', 'H2 12m CE'):
        d = DAILY[f'{name} | {mk}']; yrs = (d.index[-1] - d.index[0]).days / 365.25
        hh = d.h_eff.reindex(R.date).fillna(0).values
        CARRY[mk][name] = dict(hedge_leg_carry_bp_yr=1e4 * float((hh * R.spread_pct.values / 100).sum()) / yrs, roll_tx_bp_yr=1e4 * d.cost_roll.sum() / yrs, rolls=len(R))
    CARRY[mk]['mean_r_minus_q'] = float(R.r_minus_q.mean()); CARRY[mk]['last4'] = R.tail(4)[['date', 'old', 'new', 'spread', 'r_minus_q']].astype(str).to_dict('records')
    # ---- drawdown episodes of the book (>15%)
    u = (1 + DAILY[f'Unhedged | {mk}'].r).cumprod(); dd = u / u.cummax() - 1
    eps = []; st = None
    for t_, v in dd.items():
        if v == 0:
            if st is not None:
                seg = dd[st:t_]
                if seg.min() < -0.15: eps.append((pk, seg.idxmin()))
                st = None
            pk = t_
        elif st is None: st = t_
    if st is not None and dd[st:].min() < -0.15: eps.append((pk, dd[st:].idxmin()))
    EPS[mk] = []
    for p0, tr in eps:
        row = dict(peak=str(p0.date()), trough=str(tr.date()))
        for name in ('Unhedged', 'Static 50%', 'H1 Percentile', 'H2 12m CE'):
            e = (1 + DAILY[f'{name} | {mk}'].r).cumprod(); row[name] = 100 * (e[tr] / e[p0] - 1)
        hh = DAILY[f'H1 Percentile | {mk}'].h_eff; row['h1_peak'] = 100 * hh[p0]; row['h1_avg'] = 100 * hh[p0:tr].mean()
        EPS[mk].append(row)
    print(mk, 'done', start.date())

# ---- combined book: equal notional in the four markets, from the first day all four trade
P = {}
for name in RULES:
    r = pd.concat({mk: DAILY[f'{name} | {mk}'].r for mk in MARKETS}, axis=1).dropna()
    h = pd.concat({mk: DAILY[f'{name} | {mk}'].h_eff for mk in MARKETS}, axis=1).reindex(r.index)
    im = pd.concat({mk: DAILY[f'{name} | {mk}'].im for mk in MARKETS}, axis=1).reindex(r.index)
    rh = pd.concat({mk: DAILY[f'{name} | {mk}'].r_hedge for mk in MARKETS}, axis=1).reindex(r.index)
    cr = pd.concat({mk: DAILY[f'{name} | {mk}'].cost_roll + DAILY[f'{name} | {mk}'].cost_rebal for mk in MARKETS}, axis=1).reindex(r.index)
    d = pd.DataFrame({'r': r.mean(axis=1), 'h_eff': h.mean(axis=1), 'im': im.mean(axis=1), 'r_hedge': rh.mean(axis=1),
                      'cost_roll': cr.mean(axis=1), 'cost_rebal': 0.0})
    DAILY[f'{name} | 4-market book'] = d
    P[name] = {p: pstats(d, lo, hi) for p, lo, hi in (('full', None, None), ('fit', None, FIT_END), ('test', TEST0, None))}
RES['4-market book'] = P


def clean(o):
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list): return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)): return None if np.isnan(o) else round(float(o), 4)
    if isinstance(o, np.integer): return int(o)
    return o
json.dump(clean(dict(results=RES, regimes=REG, null=NULL, situation=SIT, carry=CARRY, episodes=EPS)), open(f'{OUT}/backtest_results.json', 'w'), indent=1)
dd = {}
for k in ('Unhedged', 'Static 50%', 'H1 Percentile'):
    e = (1 + DAILY[f'{k} | 4-market book'].r).cumprod(); dd[k] = 100 * (e / e.cummax() - 1)
pd.DataFrame(dd).resample('W-FRI').last().round(2).to_csv(f'{OUT}/book4_drawdowns_weekly.csv')
pd.DataFrame({mk: DAILY[f'H1 Percentile | {mk}'].h_eff for mk in MARKETS}).resample('W-FRI').last().round(3).to_csv(f'{OUT}/h1_ratio_weekly_4markets.csv')
print('saved')
