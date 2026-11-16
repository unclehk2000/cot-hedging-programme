"""This week's hedge: run after each CFTC release (Friday 15:30 ET, or the following business day in a holiday week).

Reads data/cot/ and quotes.json. Prints the hedge per market for every rule, the contracts on a 10-contract book,
the dealing-range quadrants (12 / 6 / 3 months), the DX and ZN readings, roll carry and margin, and writes
results/this_week.json and results/roll_schedule.csv."""
import json
import os

import numpy as np
import pandas as pd

import hedge_lib as H
from config import RESULTS_DIR, MARKETS, MACRO_CODES, MULT, BOOK_CONTRACTS, load_quotes


def ordinal(p):
    n = int(round(100 * p))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    q = load_quotes()
    tau = (H.expiry_of(q['next']) - H.expiry_of(q['front'])).days / 365.0
    out = {'quotes_date': q['date'], 'markets': {}, 'macro': {}}
    for mk in MARKETS:
        c = H.load_cot(mk)
        s = H.signals(c)
        last = s.iloc[[-1]]
        asof = last.index[0]
        rel = c.release.iloc[-1]
        hedge = {k: float(np.asarray(f(last))[0]) for k, f in H.RULES.items()}
        m = q['markets'][mk]
        notional = m['front'] * MULT[mk]
        quads = {f'{n}w': H.quadrant(float(H.range_pos(c.comm_pct, n).iloc[-1])) for n in (52, 26, 13)}
        out['markets'][mk] = dict(
            asof=str(asof.date()), release=str(rel.date()), trade=str(H.trade_date(rel).date()),
            am_pct=float(last.am_pct.iloc[0]), am_p52=float(last.am_pct_p52.iloc[0]),
            comm_pct=float(last.comm_pct.iloc[0]), comm_p52=float(last.comm_pct_p52.iloc[0]),
            score=float(last.p52.iloc[0]), r52=float(last.r52.iloc[0]), r26=float(last.r26.iloc[0]),
            composite_quadrant_26w=H.quadrant(float(last.r26.iloc[0])), comm_only_quadrants=quads,
            hedge=hedge, contracts={k: int(round(v * BOOK_CONTRACTS + 1e-9)) for k, v in hedge.items()},
            front=m['front'], next=m['next'], spread=m['next'] - m['front'], usd_roll=(m['next'] - m['front']) * MULT[mk],
            r_minus_q=100 * np.log(m['next'] / m['front']) / tau,
            initial_margin=m['initial_margin'], maintenance_margin=m['maintenance_margin'],
            notional=notional, im_pct=100 * m['initial_margin'] / notional)
    for mk, code in MACRO_CODES.items():
        p = H.load_macro_comm(code)
        r = {f'{n}w': float(H.range_pos(p, n).iloc[-1]) for n in (52, 26, 13)}
        out['macro'][mk] = dict(asof=str(p.index[-1].date()), comm_pct=float(p.iloc[-1]),
                                range_pos=r, quadrants={k: H.quadrant(v) for k, v in r.items()})
    json.dump(out, open(f'{RESULTS_DIR}/this_week.json', 'w'), indent=1)

    # next four rolls, carried at today's spread
    first = H.expiry_of(q['front'])
    rows = []
    months = ['H', 'M', 'U', 'Z']
    con = q['front']
    for _ in range(4):
        i = months.index(con[0])
        yy = int(con[1:]) + (1 if con[0] == 'Z' else 0)
        nxt = f"{months[(i + 1) % 4]}{yy:02d}"
        row = dict(roll=str(H.roll_date(con).date()), from_=con, to=nxt)
        for mk in MARKETS:
            row[f'{mk}_pts'] = round(out['markets'][mk]['spread'], 2)
            row[f'{mk}_usd'] = round(out['markets'][mk]['usd_roll'])
        rows.append(row)
        con = nxt
    pd.DataFrame(rows).to_csv(f'{RESULTS_DIR}/roll_schedule.csv', index=False)

    # print
    m0 = out['markets'][MARKETS[0]]
    print(f"COT as of {m0['asof']}, released {m0['release']}, trade at the {m0['trade']} settlement. Quotes {q['date']}.\n")
    print(f"{'':6}{'AM %OI (pct)':>16}{'Comm %OI (pct)':>17}{'Static':>8}{'H1':>6}{'H2':>6}{'H3':>6}{'H4':>6}   contracts S/H1/H2/H3/H4")
    for mk, d in out['markets'].items():
        h = d['hedge']
        n = d['contracts']
        print(f"{mk:6}{d['am_pct']:+8.1f}% ({ordinal(d['am_p52']):>4}){d['comm_pct']:+8.1f}% ({ordinal(d['comm_p52']):>4})"
              f"{100 * h['Static 50%']:7.0f}%{100 * h['H1']:5.0f}%{100 * h['H2']:5.0f}%{100 * h['H3']:5.0f}%{100 * h['H4']:5.0f}%"
              f"   {n['Static 50%']}/{n['H1']}/{n['H2']}/{n['H3']}/{n['H4']}")
    print('\nCommercials-only quadrants (12m / 6m / 3m), 1 = bottom ... 4 = top:')
    for mk, d in out['markets'].items():
        qd = d['comm_only_quadrants']
        print(f"  {mk:4} Q{qd['52w']} / Q{qd['26w']} / Q{qd['13w']}   composite 6m: Q{d['composite_quadrant_26w']}")
    for mk, d in out['macro'].items():
        qd = d['quadrants']
        print(f"  {mk:4} Q{qd['52w']} / Q{qd['26w']} / Q{qd['13w']}   commercials {d['comm_pct']:+.1f}% of OI")
    print(f"\nRoll {q['front']} -> {q['next']} on {rows[0]['roll']}:")
    for mk, d in out['markets'].items():
        print(f"  {mk:4} {d['spread']:8.2f} pts  ${d['usd_roll']:>8,.0f}/contract  r-q {d['r_minus_q']:.2f}%/yr  "
              f"IM ${d['initial_margin']:,} ({d['im_pct']:.1f}% of notional)")


if __name__ == '__main__':
    main()
