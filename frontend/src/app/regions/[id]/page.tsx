import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { api, monthLabel, pct, regionTitle, usd, usdChange } from "@/lib/api";
import { Delta, RankMeter, SourceNote, StatTile } from "@/components/ui";
import ZipExplorer from "@/components/ZipExplorer";
import Affordability from "@/components/Affordability";
import SaveButton from "@/components/SaveButton";
import RecordVisit from "@/components/RecordVisit";
import PastForecasts from "@/components/PastForecasts";
import ValueChart from "@/components/ValueChart";
import HeatCharts from "@/components/HeatCharts";

export async function generateMetadata({ params }: PageProps<"/regions/[id]">): Promise<Metadata> {
  const { id } = await params;
  const d = /^\d+$/.test(id) ? await api.region(id) : null;
  return { title: d ? regionTitle(d.region) : "Not found" };
}

// The value a year ago is today's value less the change, so the dollar amount is measured on that base.
function pastChange(value: number | null, changePct: number | null) {
  if (value == null || changePct == null) return "—";
  return usdChange(value / (1 + changePct / 100), changePct);
}

export default async function RegionPage({ params }: PageProps<"/regions/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const detail = await api.region(id);
  if (!detail) notFound();
  const r = detail.region;
  const isZip = r.kind === "zip";
  const [zips, ov] = await Promise.all([
    r.kind === "msa" ? api.zips({ metro_id: r.id, sort: "relative", limit: 1000 }) : null,
    api.overview(),
  ]);
  const zillow12 = detail.zillow_forecast.at(-1);
  const horizonLabel = detail.forecast_month ? monthLabel(detail.forecast_month) : "12 months out";

  return (
    <>
      <nav className="text-sm text-ink-2" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-accent">Markets</Link>
        {isZip && r.metro_id && (
          <> / <Link href={`/regions/${r.metro_id}`} className="hover:text-accent">{r.metro_name}</Link></>
        )}
      </nav>
      <div className="eyebrow mt-4">{isZip ? `ZIP code · ${r.county ?? ""}` : r.kind === "msa" ? "Metro area" : "Nation"}</div>
      <RecordVisit id={r.id} />
      <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
        <h1 className="display text-4xl font-semibold">
          {isZip ? <><span className="tabular">{r.name}</span> <span className="text-ink-2">{r.city}, {r.state}</span></> : r.name}
        </h1>
        <div className="flex gap-2">
          <Link href={`/compare?ids=${[r.id, r.metro_id].filter(Boolean).join(",")}`} className="segment">Compare</Link>
          <SaveButton id={r.id} name={isZip ? `ZIP ${r.name}` : r.name} />
        </div>
      </div>

      <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Typical home value" value={usd(r.value)}
                  sub={detail.origin ? `as of ${monthLabel(detail.origin)}` : undefined} />
        <StatTile label="Past year" value={<Delta v={r.change_1y_pct} />}
                  sub={<>{pastChange(r.value, r.change_1y_pct)} on a typical home<br />Past 5 years <Delta v={r.change_5y_pct} /></>} />
        <StatTile label={`Forecast to ${horizonLabel}`} value={<Delta v={r.change_pct} />}
                  sub={r.change_pct == null ? undefined : (
                    <>
                      About <strong className="tabular text-ink">{usdChange(r.value, r.change_pct)}</strong> on a typical home
                      <br />
                      <span title={`${pct(r.low_pct)} to ${pct(r.high_pct)}`}>
                        80% range {usdChange(r.value, r.low_pct, true)} to {usdChange(r.value, r.high_pct, true)}
                      </span>
                    </>
                  )} />
        {zillow12 ? (
          <StatTile label="Zillow's own forecast" value={<Delta v={zillow12.growth_pct} />}
                    sub={`to ${monthLabel(zillow12.target)}, for comparison`} />
        ) : (
          <StatTile label="Zillow's own forecast" value={<span className="text-muted">—</span>} sub="Not published for this area" />
        )}
      </section>

      <section className="mt-6"><ValueChart detail={detail} /></section>

      {isZip && r.change_pct != null && (
        <section className="card mt-6 p-5">
          <h2 className="font-semibold">How the forecast is built</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <div>
              <div className="text-sm text-ink-2">{r.metro_id ? "Metro trend" : "National trend (rural ZIP)"}</div>
              <div className="text-xl font-semibold"><Delta v={r.trend_pct} /></div>
            </div>
            <div>
              <div className="text-sm text-ink-2">This ZIP vs. its {r.metro_id ? "metro" : "nation"}</div>
              <div className="text-xl font-semibold"><Delta v={r.relative_pct} /></div>
            </div>
            <div>
              <div className="text-sm text-ink-2">Rank within metro (100 = strongest)</div>
              <div className="mt-1"><RankMeter p={r.relative_rank_pct} /></div>
            </div>
          </div>
          <p className="mt-3 text-sm text-ink-2">
            One model forecasts the market&apos;s direction; a second forecasts how this ZIP will do relative to it. In
            backtests the relative ranking was the more reliable of the two.
          </p>
        </section>
      )}

      {detail.track_record?.length ? <PastForecasts items={detail.track_record} name={isZip ? `ZIP ${r.name}` : r.name} /> : null}

      {/* Keyed by region so the calculator's inputs reset when navigating between areas. */}
      {r.value != null && <Affordability key={r.id} detail={detail} mortgageRate={ov?.mortgage_rate ?? null} />}

      {detail.heat.length > 0 && (
        <section className="mt-10">
          <h2 className="display text-2xl font-semibold">Market activity{isZip && r.metro_name ? ` in ${r.metro_name}` : ""}</h2>
          <p className="mb-4 mt-1 text-sm text-ink-2">Redfin, all residential, monthly. These feed the metro trend model.</p>
          <HeatCharts heat={detail.heat} />
        </section>
      )}

      {zips && zips.items.length > 0 && (
        <section className="mt-10">
          <h2 className="display text-2xl font-semibold">ZIP codes in this metro</h2>
          <p className="mb-4 mt-1 text-sm text-ink-2">
            Strongest forecast relative to the metro first. &ldquo;vs. metro&rdquo; ranks each ZIP within {r.name} (100 = strongest).
          </p>
          <ZipExplorer rows={zips.items} metroName={r.name} />
        </section>
      )}

      <div className="mt-10"><SourceNote /></div>
    </>
  );
}
