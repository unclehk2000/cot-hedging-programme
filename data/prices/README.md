# Price files (backtest only)

Not included: the backtest used licensed Barchart daily data. `weekly_hedge.py` doesn't need prices; only `run_backtest.py` does.

Put one file per market here, named `NQ_daily_continuous.csv`, `ES_daily_continuous.csv`, `RTY_daily_continuous.csv` and `YM_daily_continuous.csv`, with at least these columns:

| Column | Meaning |
|---|---|
| `Date` | Trading day, `YYYY-MM-DD` |
| `Contract` | Contract held that day, e.g. `nqz26` (root + month code + 2-digit year) |
| `Close` | That contract's settlement |
| `AdjClose` | Additively back-adjusted continuous price |

Build rules used in the backtest:
- one contract per day, rolled at the close of the Thursday 8 days before expiry (third Friday of Mar / Jun / Sep / Dec);
- additive back-adjustment, so `AdjClose − Close` is constant within a contract and changes by the roll spread at each roll;
- YM is used from 15 Sep 2017 (`PRICE_START` in `config.py`).

A different folder can be used with the `PRICE_DIR` environment variable.
