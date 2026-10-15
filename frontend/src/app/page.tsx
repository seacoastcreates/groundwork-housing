import Link from "next/link";
import { api, monthLabel, pct, usd, usdChange } from "@/lib/api";
import { isState } from "@/lib/states";
import { Delta, RegionCard, SourceNote, StatTile, type HeaderSort, type SortCol } from "@/components/ui";
import Search from "@/components/Search";
import StateFilter from "@/components/StateFilter";
import YourPlaces from "@/components/YourPlaces";
import DotMap from "@/components/DotMap";
import { nationLayout } from "@/lib/geo";

// Column header -> [API sort when descending, API sort when ascending]. Area sorts by size only.
const COLUMN_SORTS: Record<Exclude<SortCol, "rank">, [string, string | null]> = {
  area: ["size", null],
  value: ["value", "value_low"],
  change_1y: ["change_1y", "change_1y_low"],
  forecast: ["forecast", "forecast_low"],
};
const API_SORTS = Object.values(COLUMN_SORTS).flat().filter(Boolean) as string[];
const PAGE = 50;

// Large ZIPs only for the national lists: small ones are noisier and dominate the extremes.
const ZIP_SIZE_CUTOFF = 5000;

export default async function Home({ searchParams }: PageProps<"/">) {
  const sp = await searchParams;
  const sort = API_SORTS.includes(sp.sort as string) ? (sp.sort as string) : "size";
  const state = isState(sp.state) ? sp.state : null;
  const limit = Math.min(Math.max(PAGE, Math.round(Number(sp.n) / PAGE) * PAGE || PAGE), 1000);
  const [ov, metros, risers, laggards, mapPoints] = await Promise.all([
    api.overview(),
    api.metros({ sort, limit, state: state ?? undefined }),
    api.zips({ sort: "relative", limit: 10, max_size_rank: ZIP_SIZE_CUTOFF }),
    api.zips({ sort: "relative_low", limit: 10, max_size_rank: ZIP_SIZE_CUTOFF }),
    api.map(),
  ]);
  if (!ov || !metros) throw new Error("API unavailable");

  const href = (p: { sort?: string; n?: number }) => {
    const q = new URLSearchParams();
    const nextSort = p.sort ?? sort;
    if (nextSort !== "size") q.set("sort", nextSort);
    if (state) q.set("state", state);
    if (p.n) q.set("n", String(p.n));
    const s = q.toString();
    return s ? `/?${s}` : "/";
  };
  const sorts = Object.fromEntries(
    Object.entries(COLUMN_SORTS).map(([col, [desc, asc]]): [string, HeaderSort] => {
      const dir = sort === desc ? "desc" : sort === asc ? "asc" : null;
      // First click sorts strongest/largest first; clicking the active column flips it.
      const next = sort === desc && asc ? asc : desc;
      return [col, { dir, href: href({ sort: next, n: limit > PAGE ? limit : undefined }) }];
    }),
  ) as Partial<Record<SortCol, HeaderSort>>;
  const n = ov.nation;
  const rateChange = ov.mortgage_rate != null && ov.mortgage_rate_1y_ago != null
    ? ov.mortgage_rate - ov.mortgage_rate_1y_ago : null;

  return (
    <>
      <section className="mb-10">
        <div className="eyebrow">US housing market{ov.origin && ` · data through ${monthLabel(ov.origin)}`}</div>
        <h1 className="display mt-2 max-w-3xl text-4xl font-semibold sm:text-5xl">
          Where home values are heading, metro by metro and ZIP by ZIP
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-ink-2">
          {ov.counts.msa?.toLocaleString()} metros and {ov.counts.zip?.toLocaleString()} ZIP codes, with a 12-month
          forecast backtested against nine years of real outcomes.
        </p>
        <div className="mt-6"><Search /></div>
      </section>

      <section className="mb-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="US typical home value" value={usd(n.value)} sub={<>Past year <Delta v={n.change_1y_pct} /></>} />
        <StatTile label="Next 12 months (US)" value={<Delta v={n.change_pct} />}
                  sub={<>About <strong className="tabular text-ink">{usdChange(n.value, n.change_pct)}</strong> on a typical home<br />
                    80% range {pct(n.low_pct)} to {pct(n.high_pct)}</>} />
        <StatTile label="Past 5 years (US)" value={<Delta v={n.change_5y_pct} />} sub="Zillow Home Value Index" />
        <StatTile label="30-year mortgage rate" value={ov.mortgage_rate != null ? `${ov.mortgage_rate.toFixed(2)}%` : "—"}
                  sub={rateChange != null ? `${rateChange >= 0 ? "+" : "−"}${Math.abs(rateChange).toFixed(2)} pts vs a year ago` : undefined} />
      </section>

      <div className="mb-10"><SourceNote /></div>

      <YourPlaces />

      {mapPoints && mapPoints.length > 0 && (
        <section className="mb-12">
          <DotMap layout={nationLayout(mapPoints)} metrics={["change_pct", "change_1y_pct"]} sized
                  label={`All ${mapPoints.length} metros`} />
        </section>
      )}

      <section className="mb-12">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <h2 className="display text-2xl font-semibold">Metros{state && ` in ${state}`}</h2>
          <StateFilter value={state} />
        </div>
        <RegionCard rows={metros.items} sorts={sorts} />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
          <span>
            Showing {metros.items.length} of {metros.total} metros{state && ` in ${state}`}. Click a column to sort, or search
            to find any metro or ZIP.
          </span>
          {metros.items.length < metros.total && limit < 1000 && (
            <Link href={href({ n: limit + PAGE })} scroll={false} className="segment text-sm">
              Show {Math.min(PAGE, metros.total - metros.items.length)} more
            </Link>
          )}
        </div>
      </section>

      <section className="grid gap-12">
        {[
          ["ZIPs forecast to beat their metro", risers],
          ["ZIPs forecast to trail their metro", laggards],
        ].map(([title, list]) => (
          <div key={title as string}>
            <h2 className="display mb-1 text-2xl font-semibold">{title as string}</h2>
            <p className="mb-4 text-sm text-ink-2">
              Among the {ZIP_SIZE_CUTOFF.toLocaleString()} largest ZIPs, ranked by forecast change relative to their metro.
              The ranking is the model&apos;s strongest skill (see How it works).
            </p>
            <RegionCard rows={(list as typeof risers)?.items ?? []} showRank showMetro />
          </div>
        ))}
      </section>
    </>
  );
}
