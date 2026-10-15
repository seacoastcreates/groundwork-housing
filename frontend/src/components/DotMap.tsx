"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { pct, regionTitle, usd } from "@/lib/api";
import type { MapLayout, PlacedPoint } from "@/lib/geo";

type Metric = { key: "change_pct" | "change_1y_pct" | "relative_rank_pct"; label: string };
const METRICS: Record<Metric["key"], Metric> = {
  change_pct: { key: "change_pct", label: "Next 12 months" },
  change_1y_pct: { key: "change_1y_pct", label: "Past year" },
  relative_rank_pct: { key: "relative_rank_pct", label: "Rank vs. metro" },
};

/** Diverging color: --down below the midpoint, --up above, fading to neutral at the midpoint. */
function color(v: number | null, mid: number, span: number) {
  if (v == null) return "var(--axis)";
  const t = Math.max(-1, Math.min(1, (v - mid) / span));
  const strength = Math.round(25 + 75 * Math.abs(t));
  return `color-mix(in oklab, ${t >= 0 ? "var(--up)" : "var(--down)"} ${strength}%, var(--muted))`;
}

export default function DotMap({ layout, metrics, sized = false, label }: {
  layout: MapLayout;
  metrics: Metric["key"][];
  /** Scale dots by size rank (metros); otherwise all the same size (ZIPs). */
  sized?: boolean;
  label: string;
}) {
  const router = useRouter();
  const [metric, setMetric] = useState(metrics[0]);
  const [hover, setHover] = useState<PlacedPoint | null>(null);
  const { width, height } = layout;

  // Rank is a percentile with a natural midpoint; changes are centered on zero and scaled to the
  // 95th percentile of their magnitude so a few outliers don't wash out the rest.
  const scale = useMemo(() => {
    if (metric === "relative_rank_pct") return { mid: 50, span: 50 };
    const abs = layout.points.map((p) => Math.abs(p[metric] ?? 0)).sort((a, b) => a - b);
    return { mid: 0, span: Math.max(abs[Math.floor(abs.length * 0.95)] ?? 1, 0.5) };
  }, [layout.points, metric]);

  // Each dot with its radius, big dots first so small ones stay on top and can be hovered.
  const points = useMemo(() => {
    const maxRank = Math.max(...layout.points.map((p) => p.size_rank), 2);
    const r = (rank: number) => (sized ? 1.6 + 7.5 * (1 - Math.log(rank + 1) / Math.log(maxRank + 1)) : 4);
    // Rounded: server and browser Math.log can differ in the last digits, which breaks hydration.
    return layout.points.map((p) => ({ ...p, r: Math.round(r(p.size_rank) * 100) / 100 })).sort((a, b) => b.r - a.r);
  }, [layout.points, sized]);

  const fmt = (v: number) => (metric === "relative_rank_pct" ? `${Math.round(v)}` : pct(v, 0));
  return (
    <figure className="card p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <figcaption className="font-semibold">{label}</figcaption>
        {metrics.length > 1 && (
          <div className="flex gap-1" role="group" aria-label="Color by">
            {metrics.map((k) => (
              <button key={k} type="button" onClick={() => setMetric(k)} aria-pressed={metric === k}
                      className={`segment ${metric === k ? "segment-active" : ""}`}>{METRICS[k].label}</button>
            ))}
          </div>
        )}
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img"
             aria-label={`${label}, colored by ${METRICS[metric].label.toLowerCase()}. The tables on this page list the same areas.`}
             onMouseLeave={() => setHover(null)}>
          <path d={layout.land} fill="var(--surface-2)" stroke="none" />
          <path d={layout.borders} fill="none" stroke="var(--axis)" strokeWidth={0.6} />
          {points.map((p) => (
            <circle key={p.id} cx={p.x} cy={p.y} r={p.r} fill={color(p[metric], scale.mid, scale.span)}
                    fillOpacity={0.85} stroke={hover?.id === p.id ? "var(--ink)" : "var(--surface)"}
                    strokeWidth={hover?.id === p.id ? 1.5 : 0.5} className="cursor-pointer"
                    onMouseEnter={() => setHover(p)} onClick={() => router.push(`/regions/${p.id}`)} />
          ))}
        </svg>
        {hover && (
          <div className="pointer-events-none absolute z-10 whitespace-nowrap rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-sm"
               style={{
                 left: `${(hover.x / width) * 100}%`, top: `${(hover.y / height) * 100}%`,
                 transform: `translate(${hover.x > width * 0.6 ? "calc(-100% - 12px)" : "12px"}, -50%)`,
               }}>
            <div className="font-medium">{regionTitle(hover)}</div>
            <div className="tabular text-ink-2">{usd(hover.value)}</div>
            <div className="tabular">Next 12 months <strong>{pct(hover.change_pct)}</strong></div>
            <div className="tabular text-ink-2">Past year {pct(hover.change_1y_pct)}</div>
            {hover.relative_rank_pct != null && (
              <div className="tabular text-ink-2">Rank vs. metro {Math.round(hover.relative_rank_pct)} of 100</div>
            )}
          </div>
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
        <span className="tabular">{fmt(scale.mid - scale.span)}{metric !== "relative_rank_pct" && " or less"}</span>
        <span className="h-2 w-40 rounded-full" aria-hidden="true" style={{
          background: `linear-gradient(to right, ${color(scale.mid - scale.span, scale.mid, scale.span)}, ${color(scale.mid, scale.mid, scale.span)}, ${color(scale.mid + scale.span, scale.mid, scale.span)})`,
        }} />
        <span className="tabular">{fmt(scale.mid + scale.span)}{metric !== "relative_rank_pct" && " or more"}</span>
        <span>· Click a dot to open it{sized ? " · Larger dots are larger markets" : ""}</span>
      </div>
    </figure>
  );
}
