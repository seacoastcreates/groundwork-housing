# Hearth Index: US home values and forecasts

Typical home values for 894 metros and 26,268 ZIP codes, each with a 12-month forecast that has been
backtested against nine years of real outcomes. This is the housing counterpart to the wine price tracker
(`../wine-price-tracker`) and uses the same layers.

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router, server components), Tailwind v4, Recharts |
| API | FastAPI on Python 3.12 (read-only; forecasts are precomputed) |
| Database | PostgreSQL: `regions`, `home_values`, `market_heat`, `mortgage_rates`, `zillow_forecasts`, `model_runs`, `forecasts`, plus the `region_summary` materialized view |
| ML | `homeprice` package (LightGBM), shared by training and loading |

## Data
All of it is free bulk data. Zillow and Redfin require attribution, and their terms should be checked before
the site goes public.
- **Zillow Home Value Index (ZHVI)**: mid-tier, all home types, smoothed and seasonally adjusted. Monthly
  from 2000, for ZIPs and metros. This is what gets forecast.
- **Zillow home value forecast (ZHVF)**: only the current snapshot is published. `ingest.load` appends each
  month's snapshot to `zillow_forecasts`, so Zillow's forecasts can be scored against ours once outcomes arrive.
- **Redfin Data Center metro market tracker**: months of supply, median days on market, sale-to-list ratio
  and share of listings with a price cut. Monthly from 2012. The public file trails Zillow's by about 3 months
  (last updated 2026-06-02, through May 2026), so it is used **3 months lagged** in both the backtest and the
  live forecast.
- **FRED MORTGAGE30US**: the Freddie Mac 30-year fixed rate, averaged by month.

For the feature experiments (most were not adopted; see below):
- **Zillow**: bottom- and top-tier ZHVI by ZIP; observed rent (ZORI) by ZIP and metro, from 2015; and metro
  market data from March 2018 (for-sale inventory, new listings, new pending sales, days to pending, share of
  listings with a price cut, sale-to-list ratio). These run through the same month as ZHVI, except
  sale-to-list, which is used 1 month lagged.
- **BLS Local Area Unemployment Statistics by county**, through FRED (`LAUCN<fips>0000000004` unemployed,
  `...05` employed), from 1990. `ingest.labor` downloads them 12 series per request, which is fredgraph's
  silent cap. BLS's own bulk files refuse scripted downloads without a contact email in the User-Agent.
  Metro rates are summed from counties using the 2023 Census CBSA delineation, and ZIPs use their county.
  Lagged 1 month. BLS published no October 2025 county data because of the shutdown, so the rolling windows
  tolerate one missing month.
- **National macro from FRED**: unemployment, payrolls, CPI, the 10-year Treasury, the 10y-2y spread,
  housing starts, permits, new-home months' supply and consumer sentiment. Monthly series are lagged 1 month.

ZIPs are linked to Zillow metros by name. The ZIP file uses full CBSA names ("Houston-The Woodlands-Sugar
Land, TX") and the metro file uses short ones ("Houston, TX"); `features._short_metro` maps between them.
21,048 ZIPs get a metro parent. The rest (rural ZIPs, or small metros Zillow doesn't publish) use the nation
as their parent.

## Model
The forecast is the 12-month log change in ZHVI, split into two parts:
- **Trend model** (`TrendModel`): the change for each metro and for the nation. Inputs are the market's own
  lagged changes (1 to 60 months), national momentum, the mortgage rate and its change over 12 months, and
  Redfin market heat with year-over-year deltas. Groups that exist only for part of history are "sparse".
  One booster is trained per combination of sparse groups, on rows that have that data, and each row is
  predicted by the most complete booster it qualifies for. That way no booster learns "missing data = old
  era". With the adopted config this means a Redfin booster (2013 onward) plus a core booster for the nation
  and metros without Redfin data.
- **Relative model** (`RelativeModel`): a ZIP's change minus its parent market's change. Inputs are the
  ZIP's own history, its history relative to the parent, its price level relative to the parent and to the
  nation, the 12-month change in its monthly mortgage payment, and, where Zillow tracks rents, its
  price-to-rent ratio and rent growth relative to the parent.

Feature groups and LightGBM parameters live in `ml/homeprice/config.json`. Groups are set by
`ml/ablation.py` and parameters by `ml/tune.py`.

A ZIP's forecast is its parent's trend plus its relative forecast. The 80% ranges are empirical quantiles
of out-of-sample backtest errors.

### Why two models
The feasibility spike (2026-10-09) used one LightGBM model for each ZIP. It beat momentum on ranking in
every year from 2014 to 2025, but lost on error in 2023 and 2025 because it got the national level wrong
(a bias of −4.4 points in 2023). Splitting the forecast fixes most of that.

### Backtest (`ml/homeprice/backtest.py`)
The backtest is walk-forward. Test origins are grouped by year (2017 to 2025, quarterly), and each fold
trains only on origins whose 12-month targets were fully observed before the fold starts. Errors are in
percentage points of log change.

| | MAE | MAE 2023+ | Bias | Rank corr. |
|---|---|---|---|---|
| **Metro**: trend model with Redfin | **3.45** | **2.66** | −0.45 | 0.48 |
| Metro: trend model, prices and rates only | 4.02 | 3.93 | −1.61 | 0.48 |
| Metro: damped momentum (0.6 × last 12 months) | 4.24 | 2.70 | −2.13 | 0.40 |
| **ZIP**: two-part model | **4.16** | **3.53** | −0.23 | 0.39 |
| ZIP: damped momentum | 4.92 | 3.64 | −2.16 | 0.30 |

Ranking ZIPs within their metro (the site's headline):
- Rank correlation with actual outcomes is 0.25, against 0.12 for damped relative momentum. The model
  is better in **all 9 test years**.
- ZIPs in the top predicted decile beat their metro **70%** of the time.
- The realized gap between the top and bottom deciles is **4.0 points** over 12 months.

**Adopted:**
- Redfin heat. It lowers metro error by 14% overall and by 32% since 2023.
- The two-part split.
- Affordability and rent features in the relative model (see the feature experiments below).

### Feature experiments (`ml/ablation.py`, `ml/reports/ablation.json`)
Each group was added on its own to the baseline and run through the walk-forward backtest. The rule was
fixed before the results came in:
- **Trend group:** lower metro MAE on average, in at least two-thirds of the years it changes, and no
  worse from 2023 onward.
- **Relative group:** higher within-metro rank correlation on average and in two-thirds of years, with
  MAE no more than 1% worse.

Groups that pass are then combined, and the combination is kept only if it beats the best single group.

**Trend model:** nothing beat Redfin alone (MAE 3.445).

| Group | MAE | MAE 2023+ | Years better |
|---|---|---|---|
| shape: volatility, drawdown, trend deviation | 3.508 | 2.707 | 4/9 |
| afford: payment change, price vs nation | 3.500 | 2.757 | 4/9 |
| rent: price-to-rent, rent growth | 3.490 | 2.786 | 3/8 |
| zheat: Zillow market data, current | 3.602 | **2.504** | 2/5 |
| unemp: metro unemployment, job growth | 3.648 | 2.531 | 4/9 |
| macro: national | 3.627 | 2.981 | 4/9 |

Two groups are worth revisiting:
- **zheat** wins 2021 (3.64 vs 4.27) and 2024 (2.39 vs 3.09) but blows up 2022 (7.34 vs 4.83). With
  only 2019–2021 to learn from, it learned the boom and missed the turn. More history may fix it.
- **unemp** helps in normal years but hurts in 2020–2022, when unemployment soared while prices boomed.

National macro has only about 80 independent time points to learn from, and it overfits.

**Relative model:**
- **Round 1:** afford (rank 0.241, better in 6/9 years) and rent (0.243, 7/9) pass, and together they reach
  0.245 (8/9). Adopted. shape (2/9) and tiers (4/9) are rejected.
- **Round 2,** added later on top of round 1's winners: unemp (0.243, 4/9) and macro (0.240, 4/9) are both
  rejected.

**Disclosed fixes made during the experiments:**
- The first trend run had a gating bug: rows without Zillow market data also lost their Redfin features.
- The rule was amended so that sparse groups are judged only on the years they change.
- A few relative test rows had no target because of gaps in Zillow's series for one parent metro. The
  ablation's MAE averages had silently skipped those years. The rows are now dropped from scoring, and both
  relative rounds were re-run. The decisions didn't change.

### Hyperparameter tuning (`ml/tune.py`, `ml/reports/tuning.json`)
Optuna (TPE sampler, median pruning, study in `ml/reports/optuna.db`) searches only on early test years:
2017–2021 for trend and 2017/2019/2021 for relative, which uses a 300k-row subsample. The best parameters
and the defaults are then both scored on **2022–2025, which the search never saw**. Tuned parameters are
adopted only if they win there.

| | Search years (default → best) | Holdout default | Holdout tuned | Verdict |
|---|---|---|---|---|
| Trend (MAE) | 3.65 → 3.40 | **3.20** | 4.21 | defaults kept |
| Relative (rank corr.) | 0.271 → 0.272 | **0.228** | 0.212 | defaults kept |

The trend search found a configuration (L1 loss, 948 small trees, heavy feature subsampling) that was 7%
better on the years it was tuned on and 31% worse on 2022 onward. The holdout split exists to catch exactly
that.

**Still weak:** the two-part ZIP model loses narrowly to damped momentum in 2022, 2024 and 2025. The
national forecast comes from the core model, which has no Redfin data, and that model is the weakest piece.

## Run locally
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
createdb housingtracker
./refresh.sh                       # download (LAUS takes ~15 min), load, train (~4 min), publish
cd ml && ../.venv/bin/python -u ablation.py --write-config   # feature experiments (~40 min)
cd ml && ../.venv/bin/python -u tune.py --write-config       # Optuna search + holdout check (~30 min)
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
cd backend && ../.venv/bin/python -m pytest tests
```
The API docs are at http://localhost:8000/api/v1/docs.

## Next steps
- Deploy on AWS by reusing the wine tracker's CDK pattern (one EC2 instance, CloudFront, a monthly refresh
  run through EventBridge and SSM).
- Improve the national trend: aggregate the metro forecasts, or find a national market-heat series.
- Revisit Zillow market data (zheat) as it gains history, perhaps by training its booster on a fixed minimum
  number of years, and test unemployment with the 2020–2021 period down-weighted.
- Use real-time vintages (ALFRED) for revised series such as LAUS and payrolls.
- Add a scorecard comparing our archived forecasts with Zillow's as outcomes arrive.
- Add rent (Zillow ZORI) and county-level series.
