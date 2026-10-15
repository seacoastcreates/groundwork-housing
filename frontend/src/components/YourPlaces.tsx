"use client";

import { useEffect, useState } from "react";
import type { RegionSummary } from "@/lib/api";
import { clearList, usePlaces } from "@/lib/places";
import { RegionTable } from "@/components/ui";
import SaveButton from "@/components/SaveButton";

/** The saved and recently viewed places from this browser, shown on the home page once there are any. */
export default function YourPlaces() {
  const saved = usePlaces("saved");
  const recent = usePlaces("recent");
  const [summaries, setSummaries] = useState<Map<number, RegionSummary>>(new Map());

  const ids = [...new Set([...saved, ...recent])];
  const key = ids.join(",");
  useEffect(() => {
    if (!key) return;
    const ctrl = new AbortController();
    fetch(`/api/regions?ids=${key}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: RegionSummary[]) => setSummaries(new Map(rows.map((r) => [r.id, r]))))
      .catch(() => {});
    return () => ctrl.abort();
  }, [key]);

  const pick = (list: number[]) => list.map((id) => summaries.get(id)).filter((r): r is RegionSummary => !!r);
  const savedRows = pick(saved);
  const recentRows = pick(recent.filter((id) => !saved.includes(id)));
  if (savedRows.length === 0 && recentRows.length === 0) return null;

  const star = (r: RegionSummary) => <SaveButton id={r.id} name={r.kind === "zip" ? `ZIP ${r.name}` : r.name} compact />;
  return (
    <section className="mb-12">
      <h2 className="display mb-1 text-2xl font-semibold">Your places</h2>
      <p className="mb-4 text-sm text-ink-2">Saved and recently viewed on this device. Star any area to keep it here.</p>
      <div className="grid gap-6">
        {savedRows.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink-2">Saved</h3>
            <div className="card overflow-x-auto"><RegionTable rows={savedRows} showMetro action={star} /></div>
          </div>
        )}
        {recentRows.length > 0 && (
          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-ink-2">Recently viewed</h3>
              <button type="button" onClick={() => clearList("recent")} className="text-xs text-muted underline hover:text-ink">
                Clear
              </button>
            </div>
            <div className="card overflow-x-auto"><RegionTable rows={recentRows} showMetro action={star} /></div>
          </div>
        )}
      </div>
    </section>
  );
}
