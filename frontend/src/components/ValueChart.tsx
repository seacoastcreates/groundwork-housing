"use client";

import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RegionDetail } from "@/lib/api";
import { monthLabel, pct, usd, usdShort } from "@/lib/api";

type Row = {
  ts: number;
  month: string;
  value?: number;
  ours?: number;
  band?: [number, number];
  zillow?: number;
  zillowPct?: number;
  oursPct?: number;
};

const RANGES = { "5Y": 5, "10Y": 10, All: 99 } as const;
const ts = (d: string) => new Date(`${d.slice(0, 10)}T00:00:00`).getTime();

function Key({ color, label, band = false, dashed = false }: { color: string; label: string; band?: boolean; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-2 text-sm text-ink-2">
      {band ? (
        <span className="inline-block h-3 w-4 rounded-sm" style={{ background: color, opacity: 0.2 }} />
      ) : (
        <span className="inline-block w-4" style={{ borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}` }} />
      )}
      {label}
    </span>
  );
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-sm">
      <div className="mb-1 text-muted">{monthLabel(r.month)}</div>
      {r.value != null && <div className="tabular">Typical value <strong>{usd(r.value)}</strong></div>}
      {r.ours != null && r.oursPct != null && (
        <div className="tabular">
          Our forecast <strong>{usd(r.ours)}</strong> ({pct(r.oursPct)})
          {r.band && (
            <div className="text-xs text-muted">80% range {usd(r.band[0])} to {usd(r.band[1])}</div>
          )}
        </div>
      )}
      {r.zillow != null && r.zillowPct != null && (
        <div className="tabular">Zillow&apos;s forecast <strong>{usd(r.zillow)}</strong> ({pct(r.zillowPct)})</div>
      )}
    </div>
  );
}

export default function ValueChart({ detail }: { detail: RegionDetail }) {
  const [range, setRange] = useState<keyof typeof RANGES>("10Y");
  const { region: r, history, forecast_month, zillow_forecast, zillow_base } = detail;

  const rows = useMemo(() => {
    const last = history.at(-1);
    const out: Row[] = history.map((h) => ({ ts: ts(h.month), month: h.month, value: h.value }));
    if (!last) return out;
    const lastRow = out.at(-1)!;
    // Forecast lines start from the last observed value so they read as continuations.
    lastRow.ours = last.value;
    lastRow.band = [last.value, last.value];
    if (forecast_month && r.change_pct != null && r.low_pct != null && r.high_pct != null) {
      out.push({
        ts: ts(forecast_month),
        month: forecast_month,
        ours: last.value * (1 + r.change_pct / 100),
        oursPct: r.change_pct,
        band: [last.value * (1 + r.low_pct / 100), last.value * (1 + r.high_pct / 100)],
      });
    }
    const base = zillow_base ? history.find((h) => h.month.slice(0, 7) === zillow_base.slice(0, 7)) : undefined;
    if (base && zillow_forecast.length) {
      lastRow.zillow = last.value;
      for (const z of zillow_forecast) {
        const t = ts(z.target);
        const zillow = base.value * (1 + z.growth_pct / 100);
        const existing = out.find((o) => Math.abs(o.ts - t) < 20 * 864e5);
        if (existing) Object.assign(existing, { zillow, zillowPct: z.growth_pct });
        else out.push({ ts: t, month: z.target, zillow, zillowPct: z.growth_pct });
      }
    }
    return out.sort((a, b) => a.ts - b.ts);
  }, [history, forecast_month, zillow_forecast, zillow_base, r]);

  const lastTs = history.length ? ts(history.at(-1)!.month) : 0;
  const cutoff = lastTs - RANGES[range] * 365.25 * 864e5;
  const shown = rows.filter((row) => row.ts >= cutoff);
  // One tick per January (every other year past ten years) so labels never repeat.
  const firstYear = new Date(shown[0]?.ts ?? lastTs).getFullYear() + 1;
  const lastYear = new Date(shown.at(-1)?.ts ?? lastTs).getFullYear();
  const step = lastYear - firstYear > 12 ? 2 : 1;
  const ticks: number[] = [];
  for (let y = firstYear; y <= lastYear; y += step) ticks.push(new Date(y, 0, 1).getTime());
  const hasZillow = shown.some((row) => row.zillow != null && row.ts > lastTs);

  return (
    <figure className="card p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <figcaption className="font-semibold">Typical home value and 12-month forecast</figcaption>
        <div className="flex gap-1" role="group" aria-label="Time range">
          {(Object.keys(RANGES) as (keyof typeof RANGES)[]).map((k) => (
            <button key={k} onClick={() => setRange(k)} className={`segment ${k === range ? "segment-active" : ""}`}
                    aria-pressed={k === range}>
              {k}
            </button>
          ))}
        </div>
      </div>
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1">
        <Key color="var(--series-history)" label="Zillow Home Value Index" />
        <Key color="var(--series-forecast)" label="Our forecast" dashed />
        <Key color="var(--series-forecast)" label="80% range" band />
        {hasZillow && <Key color="var(--series-zillow)" label="Zillow's forecast" dashed />}
      </div>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={shown} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]}
                   ticks={ticks} tickFormatter={(t) => String(new Date(t).getFullYear())} stroke="var(--axis)"
                   tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} />
            <YAxis tickFormatter={usdShort} stroke="var(--axis)" tick={{ fill: "var(--muted)", fontSize: 12 }}
                   tickLine={false} axisLine={false} width={56} domain={["auto", "auto"]} />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--axis)", strokeWidth: 1 }} />
            <Area dataKey="band" stroke="none" fill="var(--series-forecast)" fillOpacity={0.18}
                  connectNulls isAnimationActive={false} />
            <Line dataKey="value" stroke="var(--series-history)" strokeWidth={2} dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} />
            <Line dataKey="zillow" stroke="var(--series-zillow)" strokeWidth={2} strokeDasharray="3 3"
                  dot={{ r: 3, strokeWidth: 0, fill: "var(--series-zillow)" }} connectNulls isAnimationActive={false} />
            <Line dataKey="ours" stroke="var(--series-forecast)" strokeWidth={2} strokeDasharray="6 4"
                  dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: "var(--series-forecast)" }}
                  connectNulls isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
