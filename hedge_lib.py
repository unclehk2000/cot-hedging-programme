"""COT hedging programme library: CFTC data, release calendar, signals, the hedge rules, prices, rolls and metrics.

Data
- COT: CFTC Public Reporting Environment (publicreporting.cftc.gov), futures only: TFF (gpe5-46if) for asset managers,
  Legacy (6dca-aqww) for commercials. Pulled by fetch_cot.py into data/cot/.
- Prices (backtest only): one contract per day, rolled at the close of the Thursday 8 days before expiry,
  additively back-adjusted. Not included in the repo; see data/prices/README.md for the format.

Timing (no look-ahead)
- COT positions are as of Tuesday and released Friday 15:30 ET. A federal holiday between the as-of day and Friday
  pushes the release to the next business day after Friday. The 2019 and 2025 shutdown backlogs use the CFTC's
  published catch-up dates.
- A hedge is traded at the settlement of the first trading day after the release and earns from the next day.
"""
import warnings

import numpy as np
import pandas as pd

from config import COT_DIR, PRICE_DIR, CODES, MULT, TICK, FEE, PRICE_START, load_quotes

warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)


# ------------------------------------------------------------------ calendar
def us_holidays(y0=2012, y1=2028):
    from pandas.tseries.holiday import USFederalHolidayCalendar
    return set(USFederalHolidayCalendar().holidays(f'{y0}-01-01', f'{y1}-12-31').date)


HOL = us_holidays()


def exchange_holidays(start, end):
    """CME equity-index full-closure days (NYSE-style calendar)"""
    from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, nearest_workday, USMartinLutherKingJr,
                                        USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay)

    class Exchange(AbstractHolidayCalendar):
        rules = [Holiday('NewYear', month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay,
                 GoodFriday, USMemorialDay, Holiday('Juneteenth', month=6, day=19, start_date='2022-01-01', observance=nearest_workday),
                 Holiday('July4', month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
                 Holiday('Christmas', month=12, day=25, observance=nearest_workday)]
    return Exchange().holidays(start, end)


def trading_days(start, end):
    return pd.bdate_range(start, end).difference(exchange_holidays(start, end))


def third_friday(y, m):
    d = pd.Timestamp(y, m, 1)
    d += pd.Timedelta(days=(4 - d.weekday()) % 7)
    return d + pd.Timedelta(days=14)


MONTH_CODE = {'h': 3, 'm': 6, 'u': 9, 'z': 12}


def expiry_of(contract):
    """'nqz26' or 'Z26' -> third Friday of Dec 2026"""
    c = contract.lower()[-3:]
    return third_friday(2000 + int(c[1:3]), MONTH_CODE[c[0]])


def roll_date(contract):
    """roll at the close of the Thursday 8 days before expiry"""
    return expiry_of(contract) - pd.Timedelta(days=8)


# CFTC catch-up publication dates (as-of -> release)
CATCHUP = {
    # 2018-19 shutdown, CFTC Release 7864-19: 24 Dec data on Fri 1 Feb 2019, then one report each Tuesday and Friday
    '2018-12-24': '2019-02-01', '2018-12-31': '2019-02-05', '2019-01-08': '2019-02-08', '2019-01-15': '2019-02-12',
    '2019-01-22': '2019-02-15', '2019-01-29': '2019-02-19', '2019-02-05': '2019-02-22', '2019-02-12': '2019-02-26',
    '2019-02-19': '2019-03-01', '2019-02-26': '2019-03-05',
    # 2025 shutdown, CFTC accelerated schedule (Nov 2025)
    '2025-09-30': '2025-11-19', '2025-10-07': '2025-11-21', '2025-10-14': '2025-11-25', '2025-10-21': '2025-12-02',
    '2025-10-28': '2025-12-05', '2025-11-04': '2025-12-09', '2025-11-10': '2025-12-10', '2025-11-18': '2025-12-12',
    '2025-11-25': '2025-12-15', '2025-12-02': '2025-12-17', '2025-12-09': '2025-12-19', '2025-12-16': '2025-12-23',
    '2025-12-23': '2025-12-29',
}


def release_date(asof):
    s = asof.strftime('%Y-%m-%d')
    if s in CATCHUP:
        return pd.Timestamp(CATCHUP[s])
    # CFTC practice (2026 schedule: Veterans Day Wed -> Mon 16 Nov, Thanksgiving -> Mon 30 Nov, Christmas Fri -> Mon 28 Dec)
    fri = asof + pd.Timedelta(days=(4 - asof.weekday()) % 7)
    days = pd.date_range(asof + pd.Timedelta(days=1), fri)
    if any(x.date() in HOL for x in days):
        d = fri + pd.Timedelta(days=1)
        while d.date() in HOL or d.weekday() >= 5:
            d += pd.Timedelta(days=1)
        return d
    return fri


def trade_date(release):
    """first exchange trading day strictly after the release day"""
    td = trading_days(release, release + pd.Timedelta(days=14))
    return td[td > release][0]


# ------------------------------------------------------------------ COT
def _rows(df, mk):
    if mk != 'RTY':
        return df[df.cftc_contract_market_code == CODES[mk]].copy()
    # Russell: ICE mini (23977A) until CME's E-mini (239742) open interest overtakes it (12 Sep 2017), then CME
    ice = df[df.cftc_contract_market_code == CODES['RTY_ICE']].set_index('report_date_as_yyyy_mm_dd')
    cme = df[df.cftc_contract_market_code == CODES['RTY']].set_index('report_date_as_yyyy_mm_dd')
    both = cme.index.intersection(ice.index)
    over = [d for d in sorted(both) if cme.loc[d, 'open_interest_all'] > ice.loc[d, 'open_interest_all']]
    switch = over[0] if over else cme.index.min()
    return pd.concat([ice[ice.index < switch], cme[cme.index >= switch]]).reset_index()


def load_cot(mk='NQ'):
    """weekly frame indexed by the Tuesday as-of date: open interest, asset-manager and commercial net positions,
    both as % of open interest, and the release date"""
    t = pd.read_csv(f'{COT_DIR}/cftc_tff_futures_only.csv', dtype={'cftc_contract_market_code': str})
    l = pd.read_csv(f'{COT_DIR}/cftc_legacy_futures_only.csv', dtype={'cftc_contract_market_code': str})
    t = _rows(t, mk)
    l = _rows(l, mk)
    for x in (t, l):
        x['asof'] = pd.to_datetime(x.report_date_as_yyyy_mm_dd.str[:10])
    t = t.set_index('asof').sort_index()
    l = l.set_index('asof').sort_index()
    c = pd.DataFrame(index=t.index)
    c['oi'] = t.open_interest_all
    c['am_net'] = t.asset_mgr_positions_long - t.asset_mgr_positions_short
    c['lev_net'] = t.lev_money_positions_long - t.lev_money_positions_short
    c['dealer_net'] = t.dealer_positions_long_all - t.dealer_positions_short_all
    c['comm_net'] = (l.comm_positions_long_all - l.comm_positions_short_all).reindex(c.index)
    c['oi_leg'] = l.open_interest_all.reindex(c.index)
    c['am_pct'] = 100 * c.am_net / c.oi
    c['comm_pct'] = 100 * c.comm_net / c.oi_leg
    c['release'] = [release_date(d) for d in c.index]
    return c


def load_macro_comm(code):
    """commercials net % of open interest for a Legacy market in the DX / ZN file"""
    d = pd.read_csv(f'{COT_DIR}/cftc_legacy_futures_only_DX_ZN.csv', dtype={'cftc_contract_market_code': str})
    d = d[d.cftc_contract_market_code == code].copy()
    d['asof'] = pd.to_datetime(d.report_date_as_yyyy_mm_dd.str[:10])
    d = d.set_index('asof').sort_index()
    return 100 * (d.comm_positions_long_all - d.comm_positions_short_all) / d.open_interest_all


# ------------------------------------------------------------------ signals
def pct_rank(x, n=52):
    """share of the trailing n weeks (current week included) at or below the current value, scaled 0..1"""
    v = x.values
    out = np.full(len(v), np.nan)
    for i in range(n - 1, len(v)):
        w = v[i - n + 1:i + 1]
        out[i] = (np.sum(w <= v[i]) - 1) / (n - 1)
    return pd.Series(out, index=x.index)


def range_pos(x, n):
    """position inside the trailing n-week range (COT index): 0 = range low, 1 = range high, 0.5 = CE"""
    lo = x.rolling(n).min()
    hi = x.rolling(n).max()
    return ((x - lo) / (hi - lo)).clip(0, 1)


def signals(c, use=('am', 'comm')):
    """bullish score in 0..1. Orientation was set in the NQ 2015-20 fit window and locked:
    Legacy commercials high = bullish; asset managers high = bearish (crowded long), so AM enters as 1 - x."""
    s = c.copy()
    for k in ('am_pct', 'comm_pct'):
        s[f'{k}_p52'] = pct_rank(s[k], 52)
        s[f'{k}_r52'] = range_pos(s[k], 52)
        s[f'{k}_r26'] = range_pos(s[k], 26)
    for w in ('p52', 'r52', 'r26'):
        parts = []
        if 'comm' in use:
            parts.append(s[f'comm_pct_{w}'])
        if 'am' in use:
            parts.append(1 - s[f'am_pct_{w}'])
        s[w] = pd.concat(parts, axis=1).mean(axis=1)
    return s


def quadrant(pos):
    """1 = bottom quarter of the range ... 4 = top quarter"""
    return int(min(np.floor(pos * 4), 3)) + 1


# ------------------------------------------------------------------ hedge rules (all read a 'bullish = high' score in 0..1)
def h_percentile(s):
    """H1: hedge = 1 - composite 52-week percentile (averages about 50%)"""
    return (1 - s['p52']).clip(0, 1)


def h_ce(s):
    """H2: the 12-month dealing range: above CE (buying) hedge 25%, below CE (selling) hedge 75%"""
    return np.where(s['r52'] >= 0.5, 0.25, 0.75)


def h_quadrant(s):
    """H3: the 6-month range in quadrants: top 0%, upper-middle 33%, lower-middle 67%, bottom 100%"""
    q = np.minimum(np.floor(s['r26'] * 4), 3)
    return np.select([q == 3, q == 2, q == 1, q == 0], [0.0, 1 / 3, 2 / 3, 1.0], np.nan)


def h_ce_quad(s):
    """H4: the 12-month CE sets the side, the 6-month quadrant sets the size"""
    q = np.minimum(np.floor(s['r26'] * 4), 3)
    above = s['r52'] >= 0.5
    return np.where(above, np.select([q == 3, q == 2, q == 1, q == 0], [0.0, 0.25, 0.5, 0.5], np.nan),
                    np.select([q == 3, q == 2, q == 1, q == 0], [0.5, 0.5, 0.75, 1.0], np.nan))


RULES = {'Static 50%': lambda s: np.full(len(s), 0.5), 'H1': h_percentile, 'H2': h_ce, 'H3': h_quadrant, 'H4': h_ce_quad}


# ------------------------------------------------------------------ prices and rolls (backtest)
def load_px(mk):
    """daily continuous file: Date, Contract (e.g. nqz26), Close, AdjClose (additively back-adjusted)"""
    d = pd.read_csv(f'{PRICE_DIR}/{mk}_daily_continuous.csv', parse_dates=['Date']).set_index('Date').sort_index()
    if mk in PRICE_START:
        d = d[d.index >= PRICE_START[mk]]
    d['off'] = d.AdjClose - d.Close
    d['ret'] = d.AdjClose.diff() / (d.AdjClose.shift(1) - d.off)      # return of the contract held today
    d['dpts'] = d.AdjClose.diff()                                       # point change of the contract held today
    return d


def rolls(d, mk):
    """one row per roll: date, old / new contract, spread (new - old) in points, spread-implied annual r - q"""
    r = []
    con = d.Contract.values
    for i in np.where(con[1:] != con[:-1])[0]:
        day = d.index[i]
        old, new = con[i], con[i + 1]
        spread = d.off.iloc[i] - d.off.iloc[i + 1]
        f_old = d.Close.iloc[i]
        f_new = f_old + spread
        tau = (expiry_of(new) - expiry_of(old)).days / 365.0
        r.append(dict(date=day, old=old, new=new, f_old=f_old, f_new=f_new, spread=spread,
                      spread_pct=100 * spread / f_old, r_minus_q=100 * np.log(f_new / f_old) / tau, tau_days=round(tau * 365),
                      usd_per_contract=spread * MULT[mk]))
    return pd.DataFrame(r)


def margin_ratio(mk):
    """initial margin as a share of one contract's notional, from quotes.json (applied back in time in the backtest)"""
    q = load_quotes()['markets'][mk]
    return q['initial_margin'] / (q['front'] * MULT[mk])


# ------------------------------------------------------------------ metrics
def equity(r):
    return (1 + r.fillna(0)).cumprod()


def max_dd(r):
    e = equity(r)
    dd = e / e.cummax() - 1
    return dd.min(), dd


def stats(df, col='r'):
    r = df[col].dropna()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    e = equity(r)
    cagr = e.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(252)
    mdd, dd = max_dd(r)
    wk = (1 + r).resample('W-FRI').prod() - 1
    cvar = wk[wk <= wk.quantile(0.05)].mean()
    ulcer = np.sqrt((100 * dd).pow(2).mean())
    return dict(cagr=100 * cagr, vol=100 * vol, sharpe=r.mean() / r.std() * np.sqrt(252), mdd=100 * mdd,
                calmar=cagr / abs(mdd), ulcer=ulcer, cvar5_wk=100 * cvar, worst_wk=100 * wk.min())


def nw_t(x, lags=4):
    """Newey-West t-stat of the mean"""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    n = len(x)
    m = x.mean()
    u = x - m
    s = u @ u / n
    for lag in range(1, lags + 1):
        g = u[lag:] @ u[:-lag] / n
        s += 2 * (1 - lag / (lags + 1)) * g
    return m / np.sqrt(s / n)


def wilson(k, n, z=1.96):
    """Wilson score interval for k hits in n trials"""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)
