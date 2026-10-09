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

ZIPs are linked to Zillow metros by name. The ZIP file uses full CBSA names ("Houston-The Woodlands-Sugar
Land, TX") and the metro file uses short ones ("Houston, TX"); `features._short_metro` maps between them.
21,048 ZIPs get a metro parent. The rest (rural ZIPs, or small metros Zillow doesn't publish) use the nation
as their parent.

## Model
The forecast is the 12-month log change in ZHVI, split into two parts:
- **Trend model** (`TrendModel`): the change for each metro and for the nation. Inputs are the market's own
  lagged changes (1 to 60 months), national momentum, the mortgage rate and its change over 12 months, and
  Redfin market heat with year-over-year deltas. The heat booster is trained only on rows that have Redfin
  data (2013 onward), so it can't learn "missing data = old era". A core booster covers the nation and any
  metro without Redfin data.
- **Relative model** (`RelativeModel`): a ZIP's change minus its parent market's change. Inputs are the
  ZIP's own history, its history relative to the parent, and its price level relative to the parent.

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
| **ZIP**: two-part model | **4.20** | **3.58** | −0.19 | 0.38 |
| ZIP: damped momentum | 4.92 | 3.64 | −2.16 | 0.30 |

Ranking ZIPs within their metro (the site's headline):
- Rank correlation with actual outcomes is 0.24, against 0.12 for damped relative momentum. The model
  is better in **all 9 test years**.
- ZIPs in the top predicted decile beat their metro **70%** of the time.
- The realized gap between the top and bottom deciles is **3.9 points** over 12 months.

**Adopted:**
- Redfin heat. It lowers metro error by 14% overall and by 32% since 2023.
- The two-part split.

**Still weak:** the two-part ZIP model loses narrowly to damped momentum in 2022, 2024 and 2025. The
national forecast comes from the core model, which has no Redfin data, and that model is the weakest piece.

## Run locally
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
createdb housingtracker
./refresh.sh                       # download, load, train (~5 min backtest + fit), publish
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
cd backend && ../.venv/bin/python -m pytest tests
```
The API docs are at http://localhost:8000/api/v1/docs.

## Next steps
- Deploy on AWS by reusing the wine tracker's CDK pattern (one EC2 instance, CloudFront, a monthly refresh
  run through EventBridge and SSM).
- Improve the national trend: aggregate the metro forecasts, or find a national market-heat series.
- Add a scorecard comparing our archived forecasts with Zillow's as outcomes arrive.
- Add rent (Zillow ZORI) and county-level series.
