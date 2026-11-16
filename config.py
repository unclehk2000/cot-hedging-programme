"""Paths and constants shared by every script. Any path can be overridden with an environment variable."""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
COT_DIR = os.environ.get('COT_DIR', os.path.join(ROOT, 'data', 'cot'))
PRICE_DIR = os.environ.get('PRICE_DIR', os.path.join(ROOT, 'data', 'prices'))
RESULTS_DIR = os.environ.get('RESULTS_DIR', os.path.join(ROOT, 'results'))
CHART_DIR = os.environ.get('CHART_DIR', os.path.join(ROOT, 'charts'))
QUOTES_FILE = os.environ.get('QUOTES_FILE', os.path.join(ROOT, 'quotes.json'))

# CFTC contract market codes
CODES = {'NQ': '209742', 'ES': '13874A', 'RTY': '239742', 'RTY_ICE': '23977A', 'YM': '124603'}
MACRO_CODES = {'DX': '098662', 'ZN': '043602'}
NAMES = {'NQ': 'E-mini Nasdaq-100', 'ES': 'E-mini S&P 500', 'RTY': 'E-mini Russell 2000', 'YM': 'E-mini Dow ($5)',
         'DX': 'US Dollar Index (ICE)', 'ZN': '10-Year T-Note (CBOT)'}

# contract specs
MULT = {'NQ': 20.0, 'ES': 50.0, 'RTY': 50.0, 'YM': 5.0}     # $ per index point
TICK = {'NQ': 5.0, 'ES': 12.5, 'RTY': 5.0, 'YM': 5.0}       # $ per tick
FEE = 2.25                                                    # $ per contract per side, commission + exchange (assumption)
PRICE_START = {'YM': '2017-09-15'}                            # first date the price file is usable, per market

MARKETS = ('NQ', 'ES', 'RTY', 'YM')
BOOK_CONTRACTS = 10                                           # contracts per book used for the sizing tables


def load_quotes(path=QUOTES_FILE):
    """latest front / next-quarter settlements and CME margins (update weekly, see quotes.json)"""
    with open(path) as f:
        return json.load(f)
