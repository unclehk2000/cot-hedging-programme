# CFTC COT data

Futures-only Commitments of Traders, Jan 2013 onwards, from the [CFTC Public Reporting Environment](https://publicreporting.cftc.gov). US government data, public domain. Refresh with `python fetch_cot.py`.

| File | Dataset | Markets |
|---|---|---|
| `cftc_tff_futures_only.csv` | TFF (`gpe5-46if`) | NQ 209742, ES 13874A, RTY 239742 (CME) and 23977A (ICE, to Sep 2017), YM 124603 |
| `cftc_legacy_futures_only.csv` | Legacy (`6dca-aqww`) | same |
| `cftc_tff_futures_only_DX_ZN.csv` | TFF | DX 098662, ZN 043602 |
| `cftc_legacy_futures_only_DX_ZN.csv` | Legacy | DX 098662, ZN 043602 |

The latest week is the 10 Nov 2026 report, checked field by field against the cftc.gov weekly reports. In the two DX / ZN files that week holds the core position fields only (open interest and each group's long / short); run `fetch_cot.py` for the full rows.
