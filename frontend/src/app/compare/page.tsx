import type { Metadata } from "next";
import { api, pct, usd, type RegionDetail } from "@/lib/api";
import { Delta, RegionLink, SourceNote } from "@/components/ui";
import CompareChart from "@/components/CompareChart";
import CompareControls from "@/components/CompareControls";
import { MAX_COMPARE } from "@/lib/compare";

export const metadata: Metadata = { title: "Compare areas" };

function parseIds(raw: string | string[] | undefined): number[] {
  const s = Array.isArray(raw) ? raw[0] : raw;
  const ids = (s ?? "").split(",").filter((x) => /^\d+$/.test(x)).map(Number);
  return [...new Set(ids)].slice(0, MAX_COMPARE);
}

const ROWS: { label: string; cell: (d: RegionDetail) => React.ReactNode }[] = [
  { label: "Typical home value", cell: (d) => <span className="tabular">{usd(d.region.value)}</span> },
  { label: "Past year", cell: (d) => <Delta v={d.region.change_1y_pct} /> },
  { label: "Past 5 years", cell: (d) => <Delta v={d.region.change_5y_pct} /> },
  {
    label: "Next 12 months",
    cell: (d) => (
      <span>
        <Delta v={d.region.change_pct} />
        {d.region.low_pct != null && (
          <span className="block text-xs text-muted tabular">80% range {pct(d.region.low_pct, 0)} to {pct(d.region.high_pct, 0)}</span>
        )}
      </span>
    ),
  },
  {
    label: "Typical rent",
    cell: (d) => d.rent ? (
      <span className="tabular">
        {usd(d.rent.rent)}/mo
        {d.rent.source === "metro" && <span className="block text-xs text-muted">metro figure</span>}
      </span>
    ) : <span className="text-muted">—</span>,
  },
  {
    label: "Price-to-rent ratio",
    // Only with the area's own rent: a ZIP's price over its metro's rent would mix two places.
    cell: (d) => d.rent?.source === "own" && d.region.value ? <span className="tabular">{(d.region.value / (d.rent.rent * 12)).toFixed(1)}</span>
      : <span className="text-muted">—</span>,
  },
  {
    label: "Rank within metro",
    cell: (d) => d.region.relative_rank_pct != null
      ? <span className="tabular">{Math.round(d.region.relative_rank_pct)} <span className="text-xs text-muted">of 100</span></span>
      : <span className="text-muted">—</span>,
  },
];

export default async function ComparePage({ searchParams }: PageProps<"/compare">) {
  const ids = parseIds((await searchParams).ids);
  const details = (await Promise.all(ids.map((id) => api.region(id)))).filter((d): d is RegionDetail => d != null);

  return (
    <>
      <div className="eyebrow">Compare</div>
      <h1 className="display mt-1 text-4xl font-semibold">Compare areas</h1>
      <p className="mt-2 max-w-2xl text-ink-2">
        Put up to {MAX_COMPARE} metros or ZIP codes side by side. The link updates as you go, so you can share the comparison.
      </p>
      <div className="mt-6">
        <CompareControls regions={details.map((d) => d.region)} />
      </div>

      {details.length > 0 && (
        <>
          <section className="mt-6"><CompareChart details={details} /></section>
          <section className="card mt-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="th"><span className="sr-only">Measure</span></th>
                  {details.map((d) => <th key={d.region.id} className="th normal-case tracking-normal"><RegionLink r={d.region} /></th>)}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.label}>
                    <th scope="row" className="td text-left font-normal text-ink-2">{row.label}</th>
                    {details.map((d) => <td key={d.region.id} className="td">{row.cell(d)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <div className="mt-10"><SourceNote /></div>
        </>
      )}
    </>
  );
}
