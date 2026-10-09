import Link from "next/link";
import { api, monthLabel, pct, usd } from "@/lib/api";
import { Delta, RegionTable, SourceNote, StatTile } from "@/components/ui";
import Search from "@/components/Search";

const SORTS = [
  ["size", "Largest"],
  ["forecast", "Strongest forecast"],
  ["forecast_low", "Weakest forecast"],
  ["change_1y", "Past year: up most"],
  ["change_1y_low", "Past year: down most"],
] as const;

// Large ZIPs only for the national lists: small ones are noisier and dominate the extremes.
const ZIP_SIZE_CUTOFF = 5000;

export default async function Home({ searchParams }: PageProps<"/">) {
  const sp = await searchParams;
  const sort = SORTS.some(([k]) => k === sp.sort) ? (sp.sort as string) : "size";
  const [ov, metros, risers, laggards] = await Promise.all([
    api.overview(),
    api.metros({ sort, limit: 50 }),
    api.zips({ sort: "relative", limit: 10, max_size_rank: ZIP_SIZE_CUTOFF }),
    api.zips({ sort: "relative_low", limit: 10, max_size_rank: ZIP_SIZE_CUTOFF }),
  ]);
  if (!ov || !metros) throw new Error("API unavailable");
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
                  sub={`80% range ${pct(n.low_pct)} to ${pct(n.high_pct)}`} />
        <StatTile label="Past 5 years (US)" value={<Delta v={n.change_5y_pct} />} sub="Zillow Home Value Index" />
        <StatTile label="30-year mortgage rate" value={ov.mortgage_rate != null ? `${ov.mortgage_rate.toFixed(2)}%` : "—"}
                  sub={rateChange != null ? `${rateChange >= 0 ? "+" : "−"}${Math.abs(rateChange).toFixed(2)} pts vs a year ago` : undefined} />
      </section>

      <div className="mb-10"><SourceNote /></div>

      <section className="mb-12">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <h2 className="display text-2xl font-semibold">Metros</h2>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Sort metros">
            {SORTS.map(([k, label]) => (
              <Link key={k} href={k === "size" ? "/" : `/?sort=${k}`} scroll={false}
                    className={`segment ${k === sort ? "segment-active" : ""}`} aria-current={k === sort ? "true" : undefined}>
                {label}
              </Link>
            ))}
          </div>
        </div>
        <RegionTable rows={metros.items} />
        <p className="mt-2 text-xs text-muted">Showing 50 of {metros.total} metros. Search to find any metro or ZIP.</p>
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
            <RegionTable rows={(list as typeof risers)?.items ?? []} showRank showMetro />
          </div>
        ))}
      </section>
    </>
  );
}
