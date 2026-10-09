import type { AblationReport, AblationRun, TuningReport } from "@/lib/api";

const GROUP_LABELS: Record<string, string> = {
  base: "Price history + rates",
  heat: "Redfin market activity (3 mo. lag)",
  shape: "Volatility & drawdown",
  afford: "Affordability (payment change, price vs. nation)",
  rent: "Rent: price-to-rent & rent growth",
  zheat: "Zillow market activity (current)",
  tiers: "Top vs. bottom tier spread",
  unemp: "Local unemployment & job growth",
  macro: "National macro (jobs, inflation, yields, starts)",
};

function labelFor(run: AblationRun, baseline: string[]) {
  const added = run.groups.filter((g) => !baseline.includes(g));
  const removed = baseline.filter((g) => !run.groups.includes(g));
  if (!added.length && removed.length) return `Without ${removed.map((g) => GROUP_LABELS[g] ?? g).join(", ")}`;
  const plus = added.map((g) => GROUP_LABELS[g] ?? g).join(" + ");
  return removed.length ? `${plus}, replacing ${removed.map((g) => GROUP_LABELS[g] ?? g).join(", ")}` : `+ ${plus}`;
}

function Verdict({ run, adopted }: { run: AblationRun; adopted: boolean }) {
  if (adopted) return <span className="font-semibold text-up">Adopted</span>;
  if (run.passes) return <span className="text-ink-2">Passed, not best</span>;
  return <span className="text-muted">Rejected</span>;
}

/** One model's ablation: baseline first, then each variant against it. */
export function AblationTable({ report, kind }: { report: AblationReport; kind: "trend" | "relative" }) {
  const base = report.baseline;
  const isTrend = kind === "trend";
  const adoptedKey = JSON.stringify([...report.adopted].sort());
  const isAdopted = (r: AblationRun) => JSON.stringify([...r.groups].sort()) === adoptedKey;
  // Adopted first, then passed, then by effect (stored key order isn't meaningful: JSONB reorders keys).
  const rows = Object.entries(report.variants).sort(([, a], [, b]) =>
    Number(isAdopted(b)) - Number(isAdopted(a)) || Number(!!b.passes) - Number(!!a.passes) ||
    (isTrend ? a.mae - b.mae : b.rank_ic - a.rank_ic));
  const d = (v: number, b: number, lowerBetter: boolean) => {
    const diff = v - b;
    const good = lowerBetter ? diff < 0 : diff > 0;
    return (
      <span className={`tabular ${Math.abs(diff) < 1e-4 ? "text-muted" : good ? "text-up" : "text-down"}`}>
        {diff > 0 ? "+" : diff < 0 ? "−" : ""}{Math.abs(diff).toFixed(3)}
      </span>
    );
  };
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className="th">Features</th>
            {isTrend ? (
              <>
                <th className="th text-right">Metro MAE</th>
                <th className="th text-right">MAE 2023+</th>
              </>
            ) : (
              <>
                <th className="th text-right">Rank corr. in metro</th>
                <th className="th text-right">MAE</th>
              </>
            )}
            <th className="th text-right">Years better</th>
            <th className="th">Verdict</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="td font-semibold">Baseline: {base.groups.map((g) => GROUP_LABELS[g] ?? g).join(" + ")}</td>
            {isTrend ? (
              <>
                <td className="td text-right tabular">{base.mae.toFixed(3)}</td>
                <td className="td text-right tabular">{base.mae_recent.toFixed(3)}</td>
              </>
            ) : (
              <>
                <td className="td text-right tabular">{base.rank_ic.toFixed(3)}</td>
                <td className="td text-right tabular">{base.mae.toFixed(3)}</td>
              </>
            )}
            <td className="td text-right text-muted">—</td>
            <td className="td">{JSON.stringify([...base.groups].sort()) === adoptedKey ? <span className="font-semibold">Kept</span> : ""}</td>
          </tr>
          {rows.map(([key, r]) => (
            <tr key={key}>
              <td className="td">{labelFor(r, base.groups)}</td>
              {isTrend ? (
                <>
                  <td className="td text-right">{d(r.mae, base.mae, true)}</td>
                  <td className="td text-right">{d(r.mae_recent, base.mae_recent, true)}</td>
                </>
              ) : (
                <>
                  <td className="td text-right">{d(r.rank_ic, base.rank_ic, false)}</td>
                  <td className="td text-right">{d(r.mae, base.mae, true)}</td>
                </>
              )}
              <td className="td text-right tabular text-ink-2">
                {r.years_active ? `${r.years_better}/${r.years_active}` : "—"}
              </td>
              <td className="td"><Verdict run={r} adopted={isAdopted(r)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const PARAM_LABELS: Record<string, string> = {
  objective: "Loss",
  n_estimators: "Trees",
  learning_rate: "Learning rate",
  num_leaves: "Leaves per tree",
  min_child_samples: "Min rows per leaf",
  subsample: "Row sample",
  colsample_bytree: "Feature sample",
  reg_lambda: "L2 penalty",
  alpha: "Huber delta",
  huber_delta: "Huber delta",
};

const fmtParam = (v: number | string) =>
  typeof v === "string" ? v.replace("regression_l1", "L1 (absolute)").replace("regression", "L2 (squared)")
    : Number.isInteger(v) ? String(v) : v < 0.01 ? v.toExponential(1) : v.toFixed(3);

export function TuningCard({ report, kind }: { report: TuningReport; kind: "trend" | "relative" }) {
  const { holdout: h } = report;
  const isTrend = kind === "trend";
  const metric = (s: { mae: number; rank_ic: number }) => (isTrend ? s.mae.toFixed(3) : s.rank_ic.toFixed(3));
  const years = Object.keys(h.default.by_year);
  const completed = report.trials.COMPLETE ?? 0;
  const pruned = report.trials.PRUNED ?? 0;
  // Postgres JSONB reorders keys, so sort by importance rather than trusting stored order.
  const top = Object.entries(report.param_importance).sort((a, b) => b[1] - a[1]).slice(0, 4);
  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">{isTrend ? "Trend model" : "Relative model"}</h3>
        <span className={h.adopt ? "text-sm font-semibold text-up" : "text-sm text-muted"}>
          {h.adopt ? "Tuned parameters adopted" : "Defaults kept: tuning didn't hold up"}
        </span>
      </div>
      <p className="mt-1 text-sm text-ink-2">
        {completed} trials completed, {pruned} stopped early. Searched on {report.tune_years.join(", ")}; judged on{" "}
        {report.holdout_years[0]}–{report.holdout_years.at(-1)} ({isTrend ? "metro MAE, lower is better" : "within-metro rank correlation, higher is better"}).
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="th">Holdout year</th>
              {years.map((y) => <th key={y} className="th text-right">{y}</th>)}
              <th className="th text-right">Mean</th>
            </tr>
          </thead>
          <tbody>
            {(["default", "tuned"] as const).map((k) => (
              <tr key={k}>
                <td className="td capitalize">{k}</td>
                {years.map((y) => <td key={y} className="td text-right tabular">{metric(h[k].by_year[y])}</td>)}
                <td className="td text-right tabular font-semibold">{metric(h[k])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <div className="font-semibold">Best parameters found</div>
          <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-ink-2">
            {Object.entries(report.best_params).filter(([k]) => k !== "subsample_freq").map(([k, v]) => (
              <div key={k} className="contents">
                <dt>{PARAM_LABELS[k] ?? k}</dt>
                <dd className="tabular text-right">{fmtParam(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
        {top.length > 0 && (
          <div>
            <div className="font-semibold">What mattered most in the search</div>
            <ul className="mt-1 space-y-1">
              {top.map(([k, v]) => (
                <li key={k} className="flex items-center gap-2 text-ink-2">
                  <span className="w-32">{PARAM_LABELS[k] ?? k}</span>
                  <span className="relative inline-block h-1.5 w-24 overflow-hidden rounded-full bg-grid">
                    <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${Math.max(v * 100, 3)}%` }} />
                  </span>
                  <span className="tabular">{Math.round(v * 100)}%</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
