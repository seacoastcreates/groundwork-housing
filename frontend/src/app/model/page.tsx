import type { Metadata } from "next";
import { api, monthLabel, type LevelMetrics } from "@/lib/api";
import { StatTile } from "@/components/ui";
import { AblationTable, NationalCard, TuningCard } from "@/components/Experiments";

export const metadata: Metadata = { title: "How it works" };

const NAMES: Record<string, string> = {
  trend: "Trend model (with Redfin market activity)",
  trend_core: "Trend model (prices and rates only)",
  damped: "Damped momentum (60% of last year's change)",
  two_part: "Two-part model (trend + relative)",
  rel: "Relative model",
  rel_damped: "Damped relative momentum",
  zero: "Moves with its metro (zero relative change)",
};

const SHORT: Record<string, string> = {
  trend: "Trend + Redfin", trend_core: "Trend, prices only", damped: "Damped momentum", two_part: "Two-part",
};

function MetricTable({ rows, cols }: {
  rows: [string, LevelMetrics][];
  cols: [keyof LevelMetrics, string, (v: number) => string][];
}) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className="th">Model</th>
            {cols.map(([, label]) => <th key={label} className="th text-right">{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, m], i) => (
            <tr key={name}>
              <td className={`td ${i === 0 ? "font-semibold" : ""}`}>{NAMES[name] ?? name}</td>
              {cols.map(([key, label, fmt]) => {
                const v = m[key] as number | null;
                return <td key={label} className="td text-right tabular">{v == null ? "—" : fmt(v)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function YearTable({ models }: { models: [string, LevelMetrics][] }) {
  const years = Object.keys(models[0][1].by_year);
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className="th">Test year</th>
            {models.map(([name]) => <th key={name} className="th text-right">{SHORT[name] ?? name}</th>)}
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const vals = models.map(([, m]) => m.by_year[y]);
            const best = Math.min(...vals);
            return (
              <tr key={y}>
                <td className="td tabular">{y}</td>
                {vals.map((v, i) => (
                  <td key={i} className={`td text-right tabular ${v === best ? "font-semibold text-accent" : "text-ink-2"}`}>
                    {v.toFixed(2)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const pts = (v: number) => v.toFixed(2);
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}`;
const corr = (v: number) => v.toFixed(2);
const share = (v: number) => `${Math.round(v * 100)}%`;

export default async function ModelPage() {
  const info = await api.model();
  if (!info?.metrics.backtest) {
    return <p className="text-ink-2">No backtest has been published yet.</p>;
  }
  const { backtest: bt, test_years, redfin_lag_months, interval, ablation, tuning, national } = info.metrics;
  const sortByMae = (o: Record<string, LevelMetrics>) => Object.entries(o).sort((a, b) => a[1].mae - b[1].mae);
  const rel = bt.relative.rel;

  return (
    <article className="max-w-4xl">
      <div className="eyebrow">How it works</div>
      <h1 className="display mt-2 text-4xl font-semibold">A forecast that admits what it can and can&apos;t do</h1>
      <p className="mt-4 text-lg text-ink-2">
        Every number below is out of sample. For each test year from {test_years[0]} to {test_years[1]}, the models were
        retrained using only data that existed at the time, then scored on what actually happened over the next 12
        months. Errors are in percentage points of 12-month change.
      </p>

      <section className="mt-8 grid gap-4 sm:grid-cols-3">
        <StatTile label="ZIP ranking within metro" value={corr(rel.rank_ic ?? 0)}
                  sub="Rank correlation, forecast vs. actual" />
        <StatTile label="Top-decile picks that beat their metro" value={share(rel.top_decile_beat ?? 0)}
                  sub="Coin flip would be about 50%" />
        <StatTile label="Top vs. bottom decile spread" value={`${(rel.decile_spread ?? 0).toFixed(1)} pts`}
                  sub="Realized 12-month gap, same metro" />
      </section>

      <h2 className="display mt-12 text-2xl font-semibold">The design: two models, not one</h2>
      <div className="mt-3 space-y-3 text-ink-2">
        <p>
          A single model forecasting each ZIP&apos;s price change did well in calm years but missed badly at turning
          points such as 2022–2023: it got the overall direction of the market wrong even while it still ranked ZIPs
          correctly. So the forecast is split in two.
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong className="text-ink">Trend model:</strong> where each metro (and the nation) is heading. Inputs are
            the metro&apos;s own price history, national momentum, mortgage rates, and Redfin market activity: months of
            supply, days on market, sale-to-list ratio and price cuts.
          </li>
          <li>
            <strong className="text-ink">Relative model:</strong> how each ZIP will do compared with its metro. Inputs
            are the ZIP&apos;s history relative to its metro, its price level relative to the metro and the nation, the
            change in its monthly mortgage payment, and (where Zillow tracks rents) its price-to-rent ratio and rent
            growth relative to the metro.
          </li>
        </ul>
        <p>A ZIP&apos;s forecast is its metro&apos;s trend plus its relative forecast. Both are LightGBM models.</p>
      </div>

      <h2 className="display mt-12 text-2xl font-semibold">Metro forecasts</h2>
      <p className="mb-4 mt-2 text-ink-2">
        Mean absolute error, bias (negative means forecasts were too low) and rank correlation across metros.
      </p>
      <MetricTable rows={sortByMae(bt.metro)} cols={[["mae", "MAE", pts], ["mae_recent", "MAE 2023+", pts],
                                                     ["bias", "Bias", signed], ["rank_ic", "Rank corr.", corr]]} />
      <div className="mt-4"><YearTable models={sortByMae(bt.metro)} /></div>

      <h2 className="display mt-12 text-2xl font-semibold">ZIP forecasts</h2>
      <MetricTable rows={sortByMae(bt.zip)} cols={[["mae", "MAE", pts], ["mae_recent", "MAE 2023+", pts],
                                                   ["bias", "Bias", signed], ["rank_ic", "Rank corr.", corr]]} />
      <div className="mt-4"><YearTable models={sortByMae(bt.zip)} /></div>

      <h2 className="display mt-12 text-2xl font-semibold">Ranking ZIPs within their metro</h2>
      <p className="mb-4 mt-2 text-ink-2">
        This is the question the site leads with: which ZIPs will do better or worse than the metro around them.
      </p>
      <MetricTable rows={sortByMae(bt.relative)} cols={[["mae", "MAE", pts], ["rank_ic", "Rank corr.", corr],
                                                        ["top_decile_beat", "Top decile beat metro", share],
                                                        ["decile_spread", "Decile spread (pts)", pts]]} />

      {ablation && (
        <>
          <h2 className="display mt-12 text-2xl font-semibold">Feature experiments</h2>
          <div className="mt-3 space-y-3 text-ink-2">
            <p>
              Each candidate feature group was added on its own and run through the same walk-forward backtest. The bar
              was set before looking at results: a trend group must lower metro error on average, in at least two-thirds
              of the years it affects, and not hurt 2023 onward; a relative group must improve the within-metro ranking
              on average and in two-thirds of years without raising error more than 1%. Groups that pass are combined,
              and the combination is kept only if it beats the best single group.
            </p>
            <p>
              One amendment, made after the first run: groups that only exist for part of history (Zillow market data
              from 2018, rent from 2015) are judged on the years they change. That run also had a bug in which rows
              without the new data lost the Redfin features too; both were fixed before the results below.
            </p>
          </div>
          {ablation.trend && (
            <>
              <h3 className="mb-3 mt-6 font-semibold">Trend model (metros)</h3>
              <AblationTable report={ablation.trend} kind="trend" />
            </>
          )}
          {ablation.relative && (
            <>
              <h3 className="mb-3 mt-6 font-semibold">Relative model (ZIPs within their metro)</h3>
              <AblationTable report={ablation.relative} kind="relative" />
            </>
          )}
          {ablation.relative_round2 && (
            <>
              <h3 className="mb-3 mt-6 font-semibold">Relative model, round 2: groups added later, on top of round 1&apos;s winners</h3>
              <AblationTable report={ablation.relative_round2} kind="relative" />
            </>
          )}
          {(ablation.trend_retest || ablation.relative_retest) && (
            <>
              <h3 className="mb-1 mt-8 font-semibold">Round 3: re-tests with fixes</h3>
              <p className="mb-3 text-sm text-ink-2">
                Zillow market data blew up in 2022 after training on about two years of history, so a data source
                now needs three years of training history before its booster is used (it is active only in 2024–2025
                here, a thin test). Unemployment hurt during the pandemic, so it was re-tested clipped to its 2005–2019
                range, and with April 2020–September 2021 readings treated as missing. Picking that window uses
                hindsight, and testing two variants raises the odds of a lucky pass; neither passed.
              </p>
              {ablation.trend_retest && <AblationTable report={ablation.trend_retest} kind="trend" />}
              {ablation.relative_retest && <div className="mt-4"><AblationTable report={ablation.relative_retest} kind="relative" /></div>}
            </>
          )}
          <p className="mt-2 text-xs text-muted">Differences are against the baseline; green is better.</p>
        </>
      )}

      {national && (
        <>
          <h2 className="display mt-12 text-2xl font-semibold">The national forecast</h2>
          <p className="mb-4 mt-3 text-ink-2">
            Redfin has no national series, so the nation is forecast without market-activity data, the weakest setup.
            The alternative is a weighted mean of the metro forecasts, which do use Redfin.{" "}
            {national.adopt
              ? "It passed the bar, so the national figure is now the weighted mean of the metro forecasts."
              : national.backtest.aggregate.mae < national.backtest.own_row.mae
                ? "It lowered average error but didn't win often enough to pass the bar, so the national figure still comes from the national series."
                : "It didn't beat the current approach, so the national figure still comes from the national series."}
          </p>
          <NationalCard report={national} />
        </>
      )}

      {tuning && (
        <>
          <h2 className="display mt-12 text-2xl font-semibold">Hyperparameter tuning</h2>
          <p className="mb-4 mt-3 text-ink-2">
            Optuna (Bayesian search with early stopping of bad trials) tuned each model using only the earlier test
            years. The best settings and the defaults were then compared on later years the search never saw, and the
            tuned settings were kept only if they won there. Tuning on the same years you report is the easiest way to
            fool yourself with a backtest.
          </p>
          <div className="space-y-4">
            {tuning.trend && <TuningCard report={tuning.trend} kind="trend" />}
            {tuning.relative && <TuningCard report={tuning.relative} kind="relative" />}
          </div>
        </>
      )}

      <h2 className="display mt-12 text-2xl font-semibold">Honest caveats</h2>
      <ul className="mt-3 list-disc space-y-2 pl-6 text-ink-2">
        <li>
          Zillow&apos;s index is smoothed, which makes momentum look stronger than it would on raw sales. Both our models
          and the baselines are scored on the same smoothed series.
        </li>
        <li>
          Redfin&apos;s public file trails Zillow&apos;s by about three months, so Redfin data is used {redfin_lag_months}{" "}
          months behind in both the backtest and the live forecast.
        </li>
        {interval && (
          <li>
            The 80% ranges come from backtest errors: for ZIPs, actual outcomes fell between {interval.zip[0].toFixed(1)}{" "}
            and +{interval.zip[1].toFixed(1)} points of the forecast 80% of the time. They are pooled across all test
            years, so expect them to be too narrow in a shock year and too wide in a calm one.
          </li>
        )}
        <li>
          Zillow publishes its own forecast. Its history isn&apos;t public, so this site archives each month&apos;s
          snapshot and will score it against ours as outcomes arrive.
        </li>
        <li>
          Unemployment (BLS, via FRED) and national macro series are revised after release, and the backtest uses
          today&apos;s revised values with a one-month publication lag. That flatters those features slightly; the
          price, listing and rate data are not materially revised.
        </li>
        <li>This is a forecast of an index for an area, not an appraisal of any particular home.</li>
      </ul>
      <p className="mt-8 text-sm text-muted">
        Model {info.model_version}, data through {monthLabel(info.origin)}.
      </p>
    </article>
  );
}
