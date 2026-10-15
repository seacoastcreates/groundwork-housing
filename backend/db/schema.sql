-- Housing tracker schema (PostgreSQL 15+)

-- One row per geography: the nation, a metro (MSA), or a ZIP code. IDs are Zillow RegionIDs.
CREATE TABLE IF NOT EXISTS regions (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('country', 'msa', 'zip')),
    name        TEXT NOT NULL,                  -- 'United States', 'Portland, ME', or the 5-digit ZIP
    state       TEXT,
    city        TEXT,                           -- ZIPs only
    county      TEXT,                           -- ZIPs only
    metro_id    INTEGER REFERENCES regions(id), -- ZIPs: parent metro, NULL when rural
    size_rank   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS regions_kind ON regions (kind, size_rank);
CREATE INDEX IF NOT EXISTS regions_metro ON regions (metro_id);

-- Zillow Home Value Index, mid tier, smoothed and seasonally adjusted. month is the first of the month.
CREATE TABLE IF NOT EXISTS home_values (
    region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    month     DATE NOT NULL,
    value     REAL NOT NULL CHECK (value > 0),
    PRIMARY KEY (region_id, month)
);

-- Redfin metro market tracker, all residential, not seasonally adjusted.
CREATE TABLE IF NOT EXISTS market_heat (
    region_id        INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    month            DATE NOT NULL,
    months_of_supply REAL,
    median_dom       REAL,
    sale_to_list     REAL,
    price_drops      REAL,
    PRIMARY KEY (region_id, month)
);

-- Zillow Observed Rent Index (typical market rent, all homes, smoothed). ZIPs and metros, from 2015.
CREATE TABLE IF NOT EXISTS rents (
    region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    month     DATE NOT NULL,
    rent      REAL NOT NULL CHECK (rent > 0),
    PRIMARY KEY (region_id, month)
);

CREATE TABLE IF NOT EXISTS mortgage_rates (
    month DATE PRIMARY KEY,
    rate  REAL NOT NULL                          -- monthly mean of the weekly 30-year fixed rate
);

-- Monthly snapshots of Zillow's own forecast, archived so it can later be scored against outcomes.
CREATE TABLE IF NOT EXISTS zillow_forecasts (
    region_id  INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    base_month DATE NOT NULL,
    target     DATE NOT NULL,
    growth_pct REAL NOT NULL,
    PRIMARY KEY (region_id, base_month, target)
);

CREATE TABLE IF NOT EXISTS model_runs (
    model_version TEXT PRIMARY KEY,
    trained_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    origin        DATE NOT NULL,                 -- last month of data the forecasts start from
    horizon       INTEGER NOT NULL,              -- months
    metrics       JSONB NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE UNIQUE INDEX IF NOT EXISTS model_runs_one_active ON model_runs (is_active) WHERE is_active;

-- Forecast log change over the horizon, split into the metro trend and the ZIP's change relative to
-- its metro. For metros and the nation, relative is 0. low/high are an empirical 80% interval.
-- relative_rank_pct is the ZIP's percentile of relative forecast among ZIPs in the same metro
-- (100 = strongest), set at publish time; NULL for metros and rural ZIPs.
CREATE TABLE IF NOT EXISTS forecasts (
    model_version TEXT NOT NULL REFERENCES model_runs(model_version) ON DELETE CASCADE,
    region_id     INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    change_pct    REAL NOT NULL,
    low_pct       REAL NOT NULL,
    high_pct      REAL NOT NULL,
    trend_pct     REAL NOT NULL,
    relative_pct  REAL NOT NULL,
    relative_rank_pct REAL,
    PRIMARY KEY (model_version, region_id)
);

-- The active model's walk-forward backtest: for each region and test origin (2017-2025, quarterly), the
-- 12-month change the model would have forecast using only data from before that date, its 80% range, and
-- what actually happened. Replaced on publish. Feeds the track record pages.
CREATE TABLE IF NOT EXISTS backtest_forecasts (
    region_id     INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    origin        DATE NOT NULL,
    predicted_pct REAL NOT NULL,
    low_pct       REAL NOT NULL,
    high_pct      REAL NOT NULL,
    actual_pct    REAL NOT NULL,
    PRIMARY KEY (region_id, origin)
);

-- One row per region: latest value, 1- and 5-year change, and the active model's forecast. The API reads
-- this instead of joining 6.7M monthly rows per request. Refreshed by ingest.load and ingest.publish.
CREATE MATERIALIZED VIEW IF NOT EXISTS region_summary AS
WITH latest AS (SELECT max(month) AS m FROM home_values
                WHERE region_id = (SELECT id FROM regions WHERE kind = 'country'))
SELECT r.*, p.name AS metro_name,
       v0.value, f.change_pct, f.low_pct, f.high_pct, f.trend_pct,
       CASE WHEN r.kind = 'zip' THEN f.relative_pct END AS relative_pct, f.relative_rank_pct,
       (v0.value / v1.value - 1) * 100 AS change_1y_pct,
       (v0.value / v5.value - 1) * 100 AS change_5y_pct
FROM regions r
CROSS JOIN latest
LEFT JOIN regions p ON p.id = r.metro_id
LEFT JOIN home_values v0 ON v0.region_id = r.id AND v0.month = latest.m
LEFT JOIN home_values v1 ON v1.region_id = r.id AND v1.month = (latest.m - INTERVAL '1 year')::date
LEFT JOIN home_values v5 ON v5.region_id = r.id AND v5.month = (latest.m - INTERVAL '5 years')::date
LEFT JOIN forecasts f ON f.region_id = r.id
     AND f.model_version = (SELECT model_version FROM model_runs WHERE is_active);
CREATE UNIQUE INDEX IF NOT EXISTS region_summary_id ON region_summary (id);
CREATE INDEX IF NOT EXISTS region_summary_kind ON region_summary (kind, size_rank);
CREATE INDEX IF NOT EXISTS region_summary_metro ON region_summary (metro_id);
