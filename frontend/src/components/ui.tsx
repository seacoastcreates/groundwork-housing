import Link from "next/link";
import { pct, usd, type RegionSummary } from "@/lib/api";

export function Delta({ v, digits = 1 }: { v: number | null; digits?: number }) {
  if (v == null) return <span className="text-muted">—</span>;
  const cls = v > 0.05 ? "text-up" : v < -0.05 ? "text-down" : "text-ink-2";
  const arrow = v > 0.05 ? "▲" : v < -0.05 ? "▼" : "";
  return (
    <span className={`tabular whitespace-nowrap ${cls}`}>
      {arrow} {pct(v, digits).replace(/^[+−]/, "")}
    </span>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="card p-5">
      <div className="text-sm font-semibold text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular">{value}</div>
      {sub && <div className="mt-1 text-sm text-ink-2">{sub}</div>}
    </div>
  );
}

/** Forecast with its 80% range, e.g. "+2.1% (−3.0 to +7.4)". */
export function ForecastCell({ r }: { r: Pick<RegionSummary, "change_pct" | "low_pct" | "high_pct"> }) {
  if (r.change_pct == null) return <span className="text-muted">—</span>;
  return (
    <span className="whitespace-nowrap">
      <Delta v={r.change_pct} />{" "}
      <span className="text-xs text-muted tabular">
        {pct(r.low_pct, 0)} to {pct(r.high_pct, 0)}
      </span>
    </span>
  );
}

/** Percentile of a ZIP's relative forecast within its metro, as a meter. */
export function RankMeter({ p }: { p: number | null }) {
  if (p == null) return <span className="text-muted">—</span>;
  const v = Math.round(p);
  return (
    <span className="inline-flex items-center gap-2" title={`Stronger than ${v}% of ZIPs in its metro`}>
      <span className="relative inline-block h-1.5 w-14 overflow-hidden rounded-full bg-grid">
        <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${Math.max(v, 3)}%` }} />
      </span>
      <span className="tabular w-8 text-right text-sm">{v}</span>
    </span>
  );
}

export function RegionLink({ r }: { r: RegionSummary }) {
  return (
    <Link href={`/regions/${r.id}`} className="font-medium hover:text-accent">
      {r.kind === "zip" ? (
        <>
          <span className="tabular">{r.name}</span>{" "}
          <span className="font-normal text-ink-2">
            {r.city}, {r.state}
          </span>
        </>
      ) : (
        r.name
      )}
    </Link>
  );
}

export type SortCol = "area" | "value" | "change_1y" | "forecast" | "rank";
export type SortDir = "asc" | "desc";
/** How a column header sorts: a link (server-sorted pages) or a click handler (client-sorted tables). */
export type HeaderSort = { dir: SortDir | null; href?: string; onClick?: () => void };

function Th({ col, label, sorts, right = false }: {
  col: SortCol;
  label: string;
  sorts?: Partial<Record<SortCol, HeaderSort>>;
  right?: boolean;
}) {
  const s = sorts?.[col];
  const cls = `th ${right ? "text-right" : ""}`;
  if (!s) return <th className={cls}>{label}</th>;
  const arrow = s.dir === "desc" ? "▼" : s.dir === "asc" ? "▲" : "";
  const inner = (
    <>
      {label}
      <span aria-hidden="true" className={`ml-1 inline-block w-2 text-[0.6rem] ${arrow ? "text-accent" : ""}`}>{arrow}</span>
    </>
  );
  const btn = `inline-flex items-center uppercase tracking-[0.06em] hover:text-ink ${s.dir ? "text-ink" : ""}`;
  return (
    <th className={cls} aria-sort={s.dir === "desc" ? "descending" : s.dir === "asc" ? "ascending" : "none"}>
      {s.href ? (
        <Link href={s.href} scroll={false} className={btn}>{inner}</Link>
      ) : (
        <button type="button" onClick={s.onClick} className={btn}>{inner}</button>
      )}
    </th>
  );
}

export function RegionTable({ rows, showRank = false, showMetro = false, sorts, stickyHeader = false }: {
  rows: RegionSummary[];
  showRank?: boolean;
  showMetro?: boolean;
  sorts?: Partial<Record<SortCol, HeaderSort>>;
  stickyHeader?: boolean;
}) {
  return (
    <table className="w-full text-sm">
      <thead className={stickyHeader ? "sticky top-0 z-10 bg-surface shadow-[0_1px_0_var(--border)]" : undefined}>
        <tr>
          <Th col="area" label="Area" sorts={sorts} />
          {showMetro && <th className="th">Metro</th>}
          <Th col="value" label="Typical value" sorts={sorts} right />
          <Th col="change_1y" label="Past year" sorts={sorts} right />
          <Th col="forecast" label="Next 12 months (80% range)" sorts={sorts} />
          {showRank && <Th col="rank" label="vs. metro" sorts={sorts} />}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="hover:bg-surface-2">
            <td className="td"><RegionLink r={r} /></td>
            {showMetro && <td className="td text-ink-2">{r.metro_name ?? "Rural"}</td>}
            <td className="td text-right tabular">{usd(r.value)}</td>
            <td className="td text-right"><Delta v={r.change_1y_pct} /></td>
            <td className="td"><ForecastCell r={r} /></td>
            {showRank && <td className="td"><RankMeter p={r.relative_rank_pct} /></td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** A RegionTable in a card. */
export function RegionCard(props: React.ComponentProps<typeof RegionTable>) {
  return (
    <div className="card overflow-x-auto">
      <RegionTable {...props} />
    </div>
  );
}

export function SourceNote() {
  return (
    <aside className="rounded-r-lg border-l-4 border-brick bg-surface-2 px-4 py-3 text-sm text-ink-2">
      <strong className="text-ink">Real data:</strong> home values are the{" "}
      <a className="underline hover:text-ink" href="https://www.zillow.com/research/data/">Zillow Home Value Index</a>{" "}
      (typical mid-tier home, all types), market activity is from the{" "}
      <a className="underline hover:text-ink" href="https://www.redfin.com/news/data-center/">Redfin Data Center</a>, and
      mortgage rates are Freddie Mac&apos;s weekly survey via FRED. Forecasts are this site&apos;s own model, not Zillow&apos;s.
    </aside>
  );
}
