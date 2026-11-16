"""Pull the CFTC Commitments of Traders data (futures only) from the CFTC Public Reporting Environment.

    python fetch_cot.py            # full history from 2013 for the four indices and DX / ZN
    python fetch_cot.py --check    # print the latest week in the layout of the cftc.gov weekly reports

Datasets (Socrata API, no key needed):
- Traders in Financial Futures (TFF), futures only: gpe5-46if (dealers, asset managers, leveraged funds, other)
- Legacy, futures only: 6dca-aqww (commercials, non-commercials, non-reportables)

After each pull, compare the --check output with the weekly reports on cftc.gov:
- TFF: https://www.cftc.gov/dea/futures/financial_lf.htm
- Legacy CME: https://www.cftc.gov/dea/futures/deacmelf.htm (NQ, ES, RTY), CBOT: deacbtlf.htm (YM, ZN), ICE: deanybtlf.htm (DX)
"""
import argparse
import io
import os

import pandas as pd
import requests

from config import COT_DIR, CODES, MACRO_CODES

BASE = 'https://publicreporting.cftc.gov/resource/{}.csv'
DATASETS = {'tff': 'gpe5-46if', 'legacy': '6dca-aqww'}
INDEX_CODES = list(CODES.values())                       # NQ, ES, RTY (CME), RTY (ICE, before Sep 2017), YM
PAGE = 50000


def pull(dataset, codes, since='2013-01-01'):
    codes_sql = ','.join(f"'{c}'" for c in codes)
    where = f"cftc_contract_market_code in({codes_sql}) AND report_date_as_yyyy_mm_dd >= '{since}T00:00:00'"
    frames, offset = [], 0
    while True:
        r = requests.get(BASE.format(DATASETS[dataset]), timeout=120, params={
            '$where': where, '$order': 'report_date_as_yyyy_mm_dd,cftc_contract_market_code', '$limit': PAGE, '$offset': offset})
        r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text), dtype={'cftc_contract_market_code': str})
        frames.append(d)
        if len(d) < PAGE:
            break
        offset += PAGE
    return pd.concat(frames, ignore_index=True)


def fetch(since):
    os.makedirs(COT_DIR, exist_ok=True)
    jobs = [('tff', INDEX_CODES, 'cftc_tff_futures_only.csv'), ('legacy', INDEX_CODES, 'cftc_legacy_futures_only.csv'),
            ('tff', list(MACRO_CODES.values()), 'cftc_tff_futures_only_DX_ZN.csv'),
            ('legacy', list(MACRO_CODES.values()), 'cftc_legacy_futures_only_DX_ZN.csv')]
    for ds, codes, fname in jobs:
        d = pull(ds, codes, since)
        d.to_csv(f'{COT_DIR}/{fname}', index=False)
        print(f'{fname}: {len(d)} rows, latest {d.report_date_as_yyyy_mm_dd.max()[:10]}')


def check():
    """latest week, in the column order of the cftc.gov weekly reports"""
    t = pd.concat([pd.read_csv(f'{COT_DIR}/{f}', dtype={'cftc_contract_market_code': str})
                   for f in ('cftc_tff_futures_only.csv', 'cftc_tff_futures_only_DX_ZN.csv')])
    l = pd.concat([pd.read_csv(f'{COT_DIR}/{f}', dtype={'cftc_contract_market_code': str})
                   for f in ('cftc_legacy_futures_only.csv', 'cftc_legacy_futures_only_DX_ZN.csv')])
    last = t.report_date_as_yyyy_mm_dd.max()
    print(f'Report as of {last[:10]}\n')
    tc = ['open_interest_all', 'dealer_positions_long_all', 'dealer_positions_short_all', 'dealer_positions_spread_all',
          'asset_mgr_positions_long', 'asset_mgr_positions_short', 'asset_mgr_positions_spread',
          'lev_money_positions_long', 'lev_money_positions_short', 'lev_money_positions_spread',
          'other_rept_positions_long', 'other_rept_positions_short', 'other_rept_positions_spread',
          'nonrept_positions_long_all', 'nonrept_positions_short_all']
    lc = ['open_interest_all', 'noncomm_positions_long_all', 'noncomm_positions_short_all', 'noncomm_postions_spread_all',
          'comm_positions_long_all', 'comm_positions_short_all', 'tot_rept_positions_long_all', 'tot_rept_positions_short',
          'nonrept_positions_long_all', 'nonrept_positions_short_all']
    names = {v: k for k, v in {**CODES, **MACRO_CODES}.items()}
    print('TFF: OI | dealer L S Sp | asset mgr L S Sp | leveraged L S Sp | other L S Sp | non-rept L S')
    for code, r in t[t.report_date_as_yyyy_mm_dd == last].set_index('cftc_contract_market_code').iterrows():
        print(f"  {names.get(code, code):8}" + ' '.join(f'{int(r[c]):,}' if pd.notna(r[c]) else '-' for c in tc))
    print('\nLegacy: OI | non-comm L S Sp | comm L S | total rept L S | non-rept L S')
    for code, r in l[l.report_date_as_yyyy_mm_dd == last].set_index('cftc_contract_market_code').iterrows():
        print(f"  {names.get(code, code):8}" + ' '.join(f'{int(r[c]):,}' if pd.notna(r[c]) else '-' for c in lc))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', default='2013-01-01')
    ap.add_argument('--check', action='store_true', help='print the latest week for the cftc.gov cross-check')
    a = ap.parse_args()
    if not a.check:
        fetch(a.since)
    check()
