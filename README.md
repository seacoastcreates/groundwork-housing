# Groundwork: US home values and forecasts

**Live at https://groundwork.36dunes.com** (API docs at `/api/v1/docs`). Source: https://github.com/seacoastcreates/groundwork-housing

Typical home values for 894 metros and 26,268 ZIP codes, each with a 12-month forecast that has been
backtested against nine years of real outcomes. This is the housing counterpart to the wine price tracker
([wine-price-tracker](https://github.com/seacoastcreates/wine-price-tracker)) and uses the same layers.

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router, server components), Tailwind v4, Recharts, d3-geo with us-atlas for the maps (projected on the server) |
| API | FastAPI on Python 3.12 (read-only; forecasts are precomputed) |
| Database | PostgreSQL: `regions`, `home_values`, `market_heat`, `rents`, `region_geo`, `mortgage_rates`, `zillow_forecasts`, `model_runs`, `forecasts`, `backtest_forecasts`, plus the `region_summary` materialized view |
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
- **Census Gazetteer ZCTA file (2024)**: an interior point for each ZIP Code Tabulation Area. ZIP codes and
  ZCTAs share codes for all but 7 of the ZIPs Zillow tracks; a metro is placed at the mean of its ZIPs' points.
  Loaded into `region_geo` for the maps (all metros on the home page, a metro's ZIPs on its page).
- **Zillow Observed Rent Index (ZORI)**: typical market rent, all home types, for about 8,400 ZIPs and 750
  metros from 2015. Loaded into `rents` for the affordability section on region pages (rent vs. buy); ZIPs
  Zillow doesn't track show their metro's rent.

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
| **ZIP**: two-part model | **4.11** | **3.47** | −0.03 | 0.41 |
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
- A national forecast built as a labor-force-weighted mean of the metro forecasts (a disclosed override; see
  the national forecast section below).

**On the site:** `train.py` also writes every out-of-sample backtest forecast, with its 80% range and the
outcome, to `backtest_forecasts.parquet`, and `ingest.publish` loads it into `backtest_forecasts`. Region pages
show that area's past forecasts against what happened, and `/track-record` summarizes accuracy, range coverage
and direction by year. `ml/export_backtest.py <version>` backfills the file for a model trained before this.

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

**Round 3, re-tests with fixes** (2026-10-11, against the adopted models). All rejected:
- **zheat**, with sparse boosters now needing 3 years of training history (`MIN_SPARSE_YEARS`): the 2022
  blowup is gone, and 2024 improves 3.09 → 2.39. But it's active only in 2024–2025 and is marginally worse
  in 2025 (2.39 vs 2.37), so it wins 1 of 2. Promising; re-check when 2026 outcomes arrive.
- **unemp, clipped** to 2005–2019 1st/99th percentiles: worse (MAE 3.665, 4/9). The pandemic damage is
  about direction, not magnitude.
- **unemp, masked** for April 2020–September 2021 (a hindsight choice of window): MAE 3.427 vs 3.445, but
  better in only 5 of 9 years. 2022 is still worse.
- **Relative model:** clipped 4/9, masked 5/9.

Testing two unemployment variants raises the chance of a lucky pass. Neither passed anyway.

### National forecast (`ml/national_experiment.py`, `ml/reports/national.json`)
Redfin has no national series, so the nation gets the core booster. The alternative is a weighted mean
of the metro forecasts:
- **Weights:** chosen on 2005–2016 by how well they rebuild the actual national 12-month change from
  actual metro changes. Metro labor force wins with a 0.34-point error, against 1.01 for labor force ×
  home value and 1.80 for equal weights.
- **Backtest, 2017–2025:** the aggregate's national MAE is **2.73** vs **3.18** for the national row and
  3.69 for damped momentum. It's better in only **5 of 9** years, one short of the rule's 6.
- **Adopted anyway, as a disclosed override** (`config.json` → `national.override`, explained on the Model
  page). The reasons:
  - With 4 overlapping forecasts a year, a 5–4 split can't separate the two approaches. The aggregate's
    wins average about 1.7 points and its losses about 0.9.
  - It's also better since 2023 (1.97 vs 2.84).
  - The national row uses the same no-market-data setup that is much worse on metros.
  - A national figure built from the metros can't contradict them. The old one said +0.1% while most
    metros were higher.
- **Rural ZIPs**, whose parent is the nation, were checked before they switched (bar: error no worse).
  Their error is **4.91 vs 5.19**, better in 6 of 9 years, so they use the aggregate too. All-ZIP
  two-part MAE drops from 4.16 to **4.11** (from 3.53 to 3.47 since 2023).
- The live national forecast is now +2.4% (80% range −2.4% to +9.0%), up from +0.1%. The median metro is
  +3.0%, and Zillow's own national forecast is +1.4%.

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

**Still weak:** the two-part ZIP model loses to damped momentum in 2024 (3.91 vs 3.33). National forecasts
rest on a small sample, with 4 forecasts per test year.

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

## Deploy on AWS (`infra/`, `deploy/`)
The CDK stack `Groundwork` (Python, us-east-1) follows the wine tracker's pattern:
- **Server:** one EC2 t4g.small (Ubuntu 24.04 arm64) running nginx → Next.js (`/`) and FastAPI
  (`/api/v1`), with PostgreSQL on the same instance. Access is through SSM only, with no SSH, and the
  security group admits only CloudFront.
- **Edge and storage:** CloudFront for HTTPS, plus S3 buckets for weekly database backups and refresh
  artifacts.
- **Budget:** a $20 monthly budget filtered to `project=groundwork`. This needs the `project` cost
  allocation tag activated in Billing.

**Monthly refresh, on the 20th:** EventBridge Scheduler → SSM Run Command → `deploy/refresh-aws.sh`
on the server. That script starts a SageMaker Processing job (`ml/sagemaker_job.py`, image
`ml/Dockerfile`, ml.t3.xlarge) which downloads every source, builds the panels, backtests and trains.
The server has 2 GB of memory, and the panels alone need about 5 GB. The server then pulls the job's raw
files and model back from S3, reloads the database (`ingest.load` streams values, peaking at about
460 MB), publishes the model, clears the site's fetch cache and takes a backup.

**FRED from AWS:** fred.stlouisfed.org refuses connections from AWS addresses, but FRED's official
API (`api.stlouisfed.org`) accepts them. `ingest/fred.py` uses the API when `FRED_API_KEY` is set and
fredgraph otherwise, as on a local machine. The job reads the key at runtime from the Secrets Manager
secret `groundwork/fred` (JSON `{"api_key": ...}`, created by hand). Its role may read only that secret.
At the API's 120 requests a minute, the county series take about an hour.

A local run of the job's container (fredgraph, no key) took about 50 minutes: 31 minutes of FRED downloads and 13 minutes
of training. Its forecasts were identical to the locally trained model.

```bash
./deploy/package.sh                       # bundle: dump of the local database (~53 MB)
cd infra && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
npx aws-cdk@2.1143.0 synth --strict && npx aws-cdk@2.1143.0 diff Groundwork
npx aws-cdk@2.1143.0 deploy Groundwork    # needs Docker running (builds the training image)
```
Any change to the source or bundle replaces the instance. It is rebuilt from scratch, restoring the
newest S3 backup, so a redeploy never rolls data back. `deploy/claude-ops-policy.json` grants the
deploying IAM user read and ops access to this stack's resources.

## Next steps
- Re-check zheat once 2026 outcomes arrive (it now needs 3 years of history and is active from 2024).
- Use real-time vintages (ALFRED) for revised series such as LAUS and payrolls.
- Score archived live forecasts, ours and Zillow's, on the track record page as outcomes arrive.
- Add county-level series.
