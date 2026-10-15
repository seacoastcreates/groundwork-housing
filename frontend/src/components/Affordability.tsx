"use client";

import { useId, useState } from "react";
import { monthLabel, pct, usd, type RegionDetail } from "@/lib/api";
import { Delta } from "@/components/ui";

// Rough national defaults; every one is editable.
const DEFAULTS = { downPct: 20, termYears: 30, taxPct: 1.0, insurancePct: 0.5, hoa: 0 };
const PMI_PCT = 0.5;          // yearly, on the loan, while the down payment is under 20%
const HOUSING_SHARE = 0.28;   // lenders' usual cap on housing costs as a share of gross income

function payment(loan: number, ratePct: number, months: number) {
  const r = ratePct / 100 / 12;
  return r === 0 ? loan / months : (loan * r) / (1 - (1 + r) ** -months);
}

/** Principal repaid over the first 12 payments. */
function firstYearPrincipal(loan: number, ratePct: number, monthly: number) {
  const r = ratePct / 100 / 12;
  let balance = loan;
  for (let i = 0; i < 12; i++) balance -= monthly - balance * r;
  return loan - balance;
}

function Field({ label, suffix, prefix, value, onChange, step = 1, min = 0, hint }: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  prefix?: string;
  suffix?: string;
  step?: number;
  min?: number;
  hint?: string;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="text-sm text-ink-2">{label}</label>
      <div className="mt-1 flex items-center rounded-lg border border-line bg-surface px-3 focus-within:border-accent">
        {prefix && <span className="text-sm text-muted">{prefix}</span>}
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          step={step}
          value={Number.isFinite(value) ? value : ""}
          onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
          className="tabular w-full bg-transparent px-1 py-2 text-sm outline-none"
        />
        {suffix && <span className="whitespace-nowrap text-sm text-muted">{suffix}</span>}
      </div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

function Line({ label, value, strong = false }: { label: string; value: number; strong?: boolean }) {
  return (
    <div className={`flex justify-between gap-4 py-1 ${strong ? "border-t border-line pt-2 font-semibold" : "text-ink-2"}`}>
      <span>{label}</span>
      <span className="tabular text-ink">{usd(value)}</span>
    </div>
  );
}

export default function Affordability({ detail, mortgageRate }: { detail: RegionDetail; mortgageRate: number | null }) {
  const r = detail.region;
  const [price, setPrice] = useState(Math.round((r.value ?? 300000) / 1000) * 1000);
  const [downPct, setDownPct] = useState(DEFAULTS.downPct);
  const [rate, setRate] = useState(mortgageRate != null ? Math.round(mortgageRate * 100) / 100 : 7);
  const [term, setTerm] = useState(DEFAULTS.termYears);
  const [taxPct, setTaxPct] = useState(DEFAULTS.taxPct);
  const [insurancePct, setInsurancePct] = useState(DEFAULTS.insurancePct);
  const [hoa, setHoa] = useState(DEFAULTS.hoa);

  const ok = [price, downPct, rate, taxPct, insurancePct, hoa].every(Number.isFinite) && price > 0;
  const down = ok ? (price * Math.min(Math.max(downPct, 0), 100)) / 100 : 0;
  const loan = ok ? price - down : 0;
  const pi = ok ? payment(loan, rate, term * 12) : 0;
  const tax = ok ? (price * taxPct) / 100 / 12 : 0;
  const insurance = ok ? (price * insurancePct) / 100 / 12 : 0;
  const pmi = ok && downPct < 20 ? (loan * PMI_PCT) / 100 / 12 : 0;
  const total = pi + tax + insurance + pmi + (ok ? hoa : 0);
  const principal = ok ? firstYearPrincipal(loan, rate, pi) / 12 : 0;
  const income = (total * 12) / HOUSING_SHARE;

  const rent = detail.rent;
  const ratio = rent && ok ? price / (rent.rent * 12) : null;
  const appreciation = ok && r.change_pct != null ? (price * r.change_pct) / 100 / 12 : null;

  return (
    <section className="mt-10">
      <h2 className="display text-2xl font-semibold">What it costs to own here</h2>
      <p className="mb-4 mt-1 text-sm text-ink-2">
        Monthly cost of buying the typical home, at today&apos;s average 30-year rate. Change any number to fit your situation.
      </p>
      <div className="card grid gap-6 p-5 lg:grid-cols-[1fr_1fr]">
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <Field label="Home price" prefix="$" value={price} onChange={setPrice} step={5000}
                   hint={`Typical home here: ${usd(r.value)}`} />
          </div>
          <div className="col-span-2">
            <label htmlFor="down" className="flex justify-between text-sm text-ink-2">
              <span>Down payment</span>
              <span className="tabular text-ink">{Number.isFinite(downPct) ? `${downPct}% · ${usd(down)}` : "—"}</span>
            </label>
            <input id="down" type="range" min={3} max={50} step={1} value={Number.isFinite(downPct) ? downPct : 20}
                   onChange={(e) => setDownPct(Number(e.target.value))} className="mt-2 w-full accent-[var(--accent)]" />
          </div>
          <Field label="Interest rate" suffix="%" value={rate} onChange={setRate} step={0.125}
                 hint={mortgageRate != null ? `30-year average now: ${mortgageRate.toFixed(2)}%` : undefined} />
          <div>
            <span className="text-sm text-ink-2" id="term-label">Loan term</span>
            <div className="mt-1 flex gap-1" role="group" aria-labelledby="term-label">
              {[30, 15].map((t) => (
                <button key={t} type="button" onClick={() => setTerm(t)} aria-pressed={term === t}
                        className={`segment flex-1 py-2 ${term === t ? "segment-active" : ""}`}>
                  {t} years
                </button>
              ))}
            </div>
          </div>
          <Field label="Property tax" suffix="% / yr" value={taxPct} onChange={setTaxPct} step={0.1} hint="US average is about 1%" />
          <Field label="Insurance" suffix="% / yr" value={insurancePct} onChange={setInsurancePct} step={0.05} />
          <Field label="HOA" prefix="$" suffix="/ mo" value={hoa} onChange={setHoa} step={25} />
        </div>

        <div>
          <div className="text-sm font-semibold text-ink-2">Monthly cost</div>
          <div className="tabular text-4xl font-semibold">{ok ? usd(total) : "—"}</div>
          <div className="mt-3 text-sm">
            <Line label="Principal and interest" value={pi} />
            <Line label="Property tax" value={tax} />
            <Line label="Insurance" value={insurance} />
            {pmi > 0 && <Line label="Mortgage insurance (under 20% down)" value={pmi} />}
            {hoa > 0 && <Line label="HOA" value={hoa} />}
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-surface-2 p-3">
              <dt className="text-ink-2">Income to qualify</dt>
              <dd className="tabular text-lg font-semibold">{ok ? usd(Math.round(income / 1000) * 1000) : "—"}</dd>
              <dd className="text-xs text-muted">a year, keeping housing at 28% of gross pay</dd>
            </div>
            <div className="rounded-lg bg-surface-2 p-3">
              <dt className="text-ink-2">Cash at closing</dt>
              <dd className="tabular text-lg font-semibold">{ok ? usd(Math.round((down + price * 0.03) / 1000) * 1000) : "—"}</dd>
              <dd className="text-xs text-muted">down payment plus about 3% in closing costs</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="card mt-4 p-5">
        <h3 className="font-semibold">Renting vs. buying</h3>
        {rent ? (
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <div>
              <div className="text-sm text-ink-2">
                Typical rent{rent.source === "metro" ? ` in ${r.metro_name}` : ""}
              </div>
              <div className="tabular text-2xl font-semibold">{usd(rent.rent)}<span className="text-base font-normal text-ink-2"> / mo</span></div>
              <div className="text-sm text-ink-2">
                Past year <Delta v={rent.change_1y_pct} /> · {monthLabel(rent.month)}
              </div>
            </div>
            <div>
              <div className="text-sm text-ink-2">Owning vs. renting, per month</div>
              <div className="tabular text-2xl font-semibold">
                {ok ? `${total >= rent.rent ? "+" : "−"}${usd(Math.abs(total - rent.rent))}` : "—"}
              </div>
              <div className="text-sm text-ink-2">
                {ok && <>About {usd(principal)} of that goes to principal in year one, building equity.</>}
              </div>
            </div>
            <div>
              <div className="text-sm text-ink-2">Price-to-rent ratio</div>
              <div className="tabular text-2xl font-semibold">{ratio ? ratio.toFixed(1) : "—"}</div>
              <div className="text-sm text-ink-2">
                {ratio == null ? null : ratio < 15 ? "Below 15: prices are low relative to rents, which tends to favor buying."
                  : ratio > 20 ? "Above 20: prices are high relative to rents, which tends to favor renting."
                  : "Between 15 and 20: neither clearly favored."}
              </div>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-ink-2">Zillow doesn&apos;t publish a rent index for this area.</p>
        )}
        {appreciation != null && ok && (
          <p className="mt-4 text-sm text-ink-2">
            Our forecast of {pct(r.change_pct)} over 12 months would add roughly {usd(Math.abs(appreciation))} a month in
            {appreciation >= 0 ? " value" : " losses"} to the owner&apos;s side, but the 80% range runs from {pct(r.low_pct)} to{" "}
            {pct(r.high_pct)}, so treat it as uncertain.
          </p>
        )}
        <p className="mt-3 text-xs text-muted">
          Estimates only. Excludes maintenance (often about 1% of the price a year), the return the down payment could
          earn elsewhere, and tax effects. Rent is the Zillow Observed Rent Index, a typical market rent for all home types.
        </p>
      </div>
    </section>
  );
}
