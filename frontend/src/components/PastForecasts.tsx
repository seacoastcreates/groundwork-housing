"use client";

import Link from "next/link";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { monthLabel, pct, type PastForecast } from "@/lib/api";

const ts = (d: string) => new Date(`${d.slice(0, 10)}T00:00:00`).getTime();

type Row = PastForecast & { ts: number; band: [number, number] };

/** This area's walk-forward backtest: what the model would have forecast at each past date, and what happened. */
export default function PastForecasts({ items, name }: { items: PastForecast[]; name: string }) {
  const rows: Row[] = items.map((p) => ({ ...p, ts: ts(p.target), band: [p.low_pct, p.high_pct] }));
  const n = rows.length;
  const inRange = rows.filter((p) => p.actual_pct >= p.low_pct && p.actual_pct <= p.high_pct).length;
  const direction = rows.filter((p) => Math.sign(p.predicted_pct) === Math.sign(p.actual_pct)).length;
  const mae = rows.reduce((a, p) => a + Math.abs(p.predicted_pct - p.actual_pct), 0) / n;
  const years: number[] = [];
  for (let y = new Date(rows[0].ts).getFullYear() + 1; y <= new Date(rows[n - 1].ts).getFullYear(); y++) years.push(y);

  return (
    <section className="mt-10">
      <h2 className="display text-2xl font-semibold">Track record here</h2>
      <p className="mb-4 mt-1 max-w-3xl text-sm text-ink-2">
        What our model would have forecast for {name} at {n} past dates, using only the data available at the time, against
        what actually happened 12 months later. <Link href="/track-record" className="underline hover:text-ink">How we score it</Link>
      </p>
      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <div className="card p-4">
          <div className="text-sm text-ink-2">Outcome inside the 80% range</div>
          <div className="tabular text-2xl font-semibold">{inRange} of {n}</div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-ink-2">Direction called right</div>
          <div className="tabular text-2xl font-semibold">{direction} of {n}</div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-ink-2">Average miss</div>
          <div className="tabular text-2xl font-semibold">{mae.toFixed(1)} pts</div>
        </div>
      </div>
      <figure className="card p-5">
        <figcaption className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
          <span className="font-semibold text-ink">12-month change, by the month it ended</span>
          <span className="flex items-center gap-2">
            <span className="inline-block w-4" style={{ borderTop: "2px solid var(--series-history)" }} />What happened
          </span>
          <span className="flex items-center gap-2">
            <span className="inline-block w-4" style={{ borderTop: "2px dashed var(--series-forecast)" }} />Our forecast at the time
          </span>
          <span className="flex items-center gap-2">
            <span className="inline-block h-3 w-4 rounded-sm" style={{ background: "var(--series-forecast)", opacity: 0.2 }} />80% range
          </span>
        </figcaption>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]}
                     ticks={years.map((y) => new Date(y, 0, 1).getTime())}
                     tickFormatter={(t) => String(new Date(t).getFullYear())} stroke="var(--axis)"
                     tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} />
              <YAxis tickFormatter={(v) => pct(v, 0)} stroke="var(--axis)" tick={{ fill: "var(--muted)", fontSize: 12 }}
                     tickLine={false} axisLine={false} width={48} />
              <Tooltip
                cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const r = payload[0].payload as Row;
                  const hit = r.actual_pct >= r.low_pct && r.actual_pct <= r.high_pct;
                  return (
                    <div className="rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-sm">
                      <div className="mb-1 text-muted">{monthLabel(r.origin)} to {monthLabel(r.target)}</div>
                      <div className="tabular">Forecast <strong>{pct(r.predicted_pct)}</strong>
                        <span className="text-muted"> ({pct(r.low_pct)} to {pct(r.high_pct)})</span></div>
                      <div className="tabular">Actual <strong>{pct(r.actual_pct)}</strong></div>
                      <div className={hit ? "text-up" : "text-down"}>{hit ? "Inside the range" : "Outside the range"}</div>
                    </div>
                  );
                }}
              />
              <Area dataKey="band" stroke="none" fill="var(--series-forecast)" fillOpacity={0.18} isAnimationActive={false} />
              <Line dataKey="actual_pct" stroke="var(--series-history)" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="predicted_pct" stroke="var(--series-forecast)" strokeWidth={2} strokeDasharray="6 4"
                    dot={{ r: 2.5, strokeWidth: 0, fill: "var(--series-forecast)" }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </figure>
    </section>
  );
}
