"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { monthLabel, pct, regionTitle, usd, usdShort, type RegionDetail } from "@/lib/api";

export const COMPARE_COLORS = ["var(--series-history)", "var(--series-forecast)", "var(--series-zillow)", "var(--series-4)"];

const RANGES = { "5Y": 5, "10Y": 10, All: 99 } as const;
type Mode = "value" | "change";
const ts = (d: string) => new Date(`${d.slice(0, 10)}T00:00:00`).getTime();

type Row = { ts: number; month: string } & Record<string, number | string | undefined>;

export default function CompareChart({ details }: { details: RegionDetail[] }) {
  const [range, setRange] = useState<keyof typeof RANGES>("10Y");
  const [mode, setMode] = useState<Mode>("change");

  const lastTs = Math.max(...details.map((d) => (d.history.length ? ts(d.history.at(-1)!.month) : 0)));
  const cutoff = lastTs - RANGES[range] * 365.25 * 864e5;

  const rows = useMemo(() => {
    const byTs = new Map<number, Row>();
    const row = (month: string) => {
      const t = ts(month);
      let r = byTs.get(t);
      if (!r) byTs.set(t, (r = { ts: t, month }));
      return r;
    };
    details.forEach((d, i) => {
      const shown = d.history.filter((h) => ts(h.month) >= cutoff);
      if (!shown.length) return;
      // "Change" mode indexes each area to its first month in view, so different price levels compare.
      const base = shown[0].value;
      const scale = (v: number) => (mode === "change" ? (v / base - 1) * 100 : v);
      for (const h of shown) row(h.month)[`v${i}`] = scale(h.value);
      const last = shown.at(-1)!;
      const r = d.region;
      if (d.forecast_month && r.change_pct != null) {
        row(last.month)[`f${i}`] = scale(last.value);
        row(d.forecast_month)[`f${i}`] = scale(last.value * (1 + r.change_pct / 100));
      }
    });
    return [...byTs.values()].sort((a, b) => a.ts - b.ts);
  }, [details, cutoff, mode]);

  const fmt = (v: number) => (mode === "change" ? pct(v, 0) : usdShort(v));
  const firstYear = new Date(rows[0]?.ts ?? lastTs).getFullYear() + 1;
  const lastYear = new Date(rows.at(-1)?.ts ?? lastTs).getFullYear();
  const step = lastYear - firstYear > 12 ? 2 : 1;
  const ticks: number[] = [];
  for (let y = firstYear; y <= lastYear; y += step) ticks.push(new Date(y, 0, 1).getTime());

  return (
    <figure className="card p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <figcaption className="font-semibold">
          {mode === "change" ? "Change in typical home value since the start of the period" : "Typical home value"}
          <span className="font-normal text-ink-2">, with each area&apos;s 12-month forecast (dashed)</span>
        </figcaption>
        <div className="flex flex-wrap gap-3">
          <div className="flex gap-1" role="group" aria-label="Scale">
            {([["change", "% change"], ["value", "$ value"]] as const).map(([k, label]) => (
              <button key={k} type="button" onClick={() => setMode(k)} aria-pressed={mode === k}
                      className={`segment ${mode === k ? "segment-active" : ""}`}>{label}</button>
            ))}
          </div>
          <div className="flex gap-1" role="group" aria-label="Time range">
            {(Object.keys(RANGES) as (keyof typeof RANGES)[]).map((k) => (
              <button key={k} type="button" onClick={() => setRange(k)} aria-pressed={range === k}
                      className={`segment ${range === k ? "segment-active" : ""}`}>{k}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1">
        {details.map((d, i) => (
          <span key={d.region.id} className="flex items-center gap-2 text-sm text-ink-2">
            <span className="inline-block w-4" style={{ borderTop: `3px solid ${COMPARE_COLORS[i]}` }} />
            {regionTitle(d.region)}
          </span>
        ))}
      </div>
      <div className="h-96">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]} ticks={ticks}
                   tickFormatter={(t) => String(new Date(t).getFullYear())} stroke="var(--axis)"
                   tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} />
            <YAxis tickFormatter={fmt} stroke="var(--axis)" tick={{ fill: "var(--muted)", fontSize: 12 }}
                   tickLine={false} axisLine={false} width={56} domain={["auto", "auto"]} />
            <Tooltip
              cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const r = payload[0].payload as Row;
                return (
                  <div className="rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-sm">
                    <div className="mb-1 text-muted">{monthLabel(r.month)}</div>
                    {details.map((d, i) => {
                      const v = (r[`v${i}`] ?? r[`f${i}`]) as number | undefined;
                      if (v == null) return null;
                      const forecast = r[`v${i}`] == null;
                      return (
                        <div key={d.region.id} className="tabular flex items-center gap-2">
                          <span className="inline-block h-2 w-2 rounded-full" style={{ background: COMPARE_COLORS[i] }} />
                          {regionTitle(d.region)}: <strong>{mode === "change" ? pct(v) : usd(v)}</strong>
                          {forecast && <span className="text-muted">forecast</span>}
                        </div>
                      );
                    })}
                  </div>
                );
              }}
            />
            {details.map((d, i) => [
              <Line key={`v${i}`} dataKey={`v${i}`} stroke={COMPARE_COLORS[i]} strokeWidth={2} dot={false}
                    connectNulls isAnimationActive={false} />,
              <Line key={`f${i}`} dataKey={`f${i}`} stroke={COMPARE_COLORS[i]} strokeWidth={2} strokeDasharray="6 4"
                    dot={false} connectNulls isAnimationActive={false} legendType="none" />,
            ])}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
