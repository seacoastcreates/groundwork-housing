"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HeatPoint } from "@/lib/api";
import { monthLabel } from "@/lib/api";

type Metric = {
  key: keyof Omit<HeatPoint, "month">;
  title: string;
  hint: string;
  fmt: (v: number) => string;
};

const METRICS: Metric[] = [
  { key: "months_of_supply", title: "Months of supply", hint: "Higher = more buyer leverage", fmt: (v) => v.toFixed(1) },
  { key: "median_dom", title: "Median days on market", hint: "Higher = slower market", fmt: (v) => `${Math.round(v)}` },
  { key: "sale_to_list", title: "Sale-to-list ratio", hint: "Above 100% = bidding wars", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "price_drops", title: "Listings with a price cut", hint: "Higher = sellers giving ground", fmt: (v) => `${(v * 100).toFixed(0)}%` },
];

function HeatTooltip({ active, payload, m }: { active?: boolean; payload?: { payload: HeatPoint }[]; m: Metric }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const v = p[m.key];
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-sm">
      <div className="text-muted">{monthLabel(p.month, true)}</div>
      <div className="tabular font-semibold">{v == null ? "—" : m.fmt(v)}</div>
    </div>
  );
}

/** Small multiples, one per Redfin metric: different units never share an axis. */
export default function HeatCharts({ heat }: { heat: HeatPoint[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {METRICS.map((m) => {
        const data = heat.filter((h) => h[m.key] != null);
        if (data.length < 6) return null;
        const latest = data.at(-1)!;
        return (
          <figure key={m.key} className="card p-4">
            <figcaption className="flex items-baseline justify-between gap-2">
              <span className="font-semibold">{m.title}</span>
              <span className="tabular text-lg font-semibold">{m.fmt(latest[m.key]!)}</span>
            </figcaption>
            <div className="mb-2 text-xs text-muted">{m.hint} · latest {monthLabel(latest.month, true)}</div>
            <div className="h-36">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <XAxis dataKey="month" tickFormatter={(d: string) => d.slice(0, 4)} stroke="var(--axis)"
                         tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} minTickGap={36} />
                  <YAxis tickFormatter={m.fmt} stroke="var(--axis)" tick={{ fill: "var(--muted)", fontSize: 11 }}
                         tickLine={false} axisLine={false} width={54} domain={["auto", "auto"]} />
                  <Tooltip content={<HeatTooltip m={m} />} cursor={{ stroke: "var(--axis)" }} />
                  <Line dataKey={m.key} stroke="var(--series-history)" strokeWidth={2} dot={false}
                        activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </figure>
        );
      })}
    </div>
  );
}
