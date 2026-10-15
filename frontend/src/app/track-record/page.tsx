import type { Metadata } from "next";
import Link from "next/link";
import { api, monthLabel, type TrackRecordRow } from "@/lib/api";
import { StatTile } from "@/components/ui";

export const metadata: Metadata = { title: "Track record" };

const LEVELS = [["metro", "Metros"], ["zip", "ZIP codes"]] as const;

function Cells({ r }: { r: TrackRecordRow | undefined }) {
  if (!r) return <><td className="td" /><td className="td" /><td className="td" /></>;
  return (
    <>
      <td className="td text-right tabular">{r.mae.toFixed(1)}</td>
      <td className="td text-right tabular">{Math.round(r.coverage_pct)}%</td>
      <td className="td text-right tabular">{Math.round(r.direction_pct)}%</td>
    </>
  );
}

export default async function TrackRecordPage() {
  const tr = await api.trackRecord();
  const rows = tr?.rows ?? [];
  const find = (period: string, level: string) => rows.find((r) => r.period === period && r.level === level);
  const years = [...new Set(rows.map((r) => r.period).filter((p) => p !== "all"))];

  return (
    <>
      <div className="eyebrow">Accountability</div>
      <h1 className="display mt-1 text-4xl font-semibold">Track record</h1>
      <p className="mt-3 max-w-3xl text-lg text-ink-2">
        How well would these forecasts have done? For every quarter from{" "}
        {tr?.first_origin ? monthLabel(tr.first_origin) : "2017"} to {tr?.last_origin ? monthLabel(tr.last_origin) : "2025"}, the
        model was trained only on data available at the time, asked for the next 12 months, and scored against what
        actually happened.
      </p>

      {rows.length === 0 ? (
        <p className="card mt-8 p-6 text-ink-2">The track record for the current model hasn&apos;t been published yet.</p>
      ) : (
        <>
          {LEVELS.map(([level, label]) => {
            const all = find("all", level);
            if (!all) return null;
            return (
              <section key={level} className="mt-8">
                <h2 className="mb-3 text-sm font-semibold text-ink-2">
                  {label} · {all.n.toLocaleString()} past forecasts
                </h2>
                <div className="grid gap-4 sm:grid-cols-3">
                  <StatTile label="Outcome inside the 80% range" value={`${Math.round(all.coverage_pct)}%`}
                            sub="80% overall by design: ranges are set from these errors. The yearly table shows where they held" />
                  <StatTile label="Direction called right" value={`${Math.round(all.direction_pct)}%`}
                            sub="Forecast and outcome both up, or both down" />
                  <StatTile label="Average miss" value={`${all.mae.toFixed(1)} pts`}
                            sub={`Forecasts ran ${all.bias >= 0 ? "high" : "low"} by ${Math.abs(all.bias).toFixed(1)} pts on average`} />
                </div>
              </section>
            );
          })}

          <section className="mt-10">
            <h2 className="display text-2xl font-semibold">Year by year</h2>
            <p className="mb-4 mt-1 text-sm text-ink-2">
              By the year each forecast was made. Misses are in percentage points of 12-month change.
            </p>
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className="th" rowSpan={2}>Forecast made in</th>
                    {LEVELS.map(([l, label]) => <th key={l} className="th text-center" colSpan={3}>{label}</th>)}
                  </tr>
                  <tr>
                    {LEVELS.flatMap(([l]) => ["Avg miss", "In range", "Direction"].map((h) => (
                      <th key={`${l}-${h}`} className="th text-right">{h}</th>
                    )))}
                  </tr>
                </thead>
                <tbody>
                  {years.map((y) => (
                    <tr key={y} className="hover:bg-surface-2">
                      <td className="td tabular">{y}</td>
                      <Cells r={find(y, "metro")} />
                      <Cells r={find(y, "zip")} />
                    </tr>
                  ))}
                  <tr className="font-semibold">
                    <td className="td">All years</td>
                    <Cells r={find("all", "metro")} />
                    <Cells r={find("all", "zip")} />
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-3 max-w-3xl text-sm text-ink-2">
              The biggest misses came from forecasts made in 2020 and 2021, when the pandemic boom outran anything in the
              history the model had seen. Ranges are set from these same backtest errors, which is why they are wide.
            </p>
          </section>

          <section className="card mt-10 p-5 text-sm text-ink-2">
            <h2 className="font-semibold text-ink">What&apos;s next</h2>
            <p className="mt-2">
              Each month&apos;s live forecasts, and Zillow&apos;s, are archived. Once their 12 months have passed, they will be
              scored here alongside the backtest. See <Link href="/model" className="underline hover:text-ink">How it works</Link> for
              the model itself and the within-metro ranking results.
            </p>
          </section>
        </>
      )}
    </>
  );
}
