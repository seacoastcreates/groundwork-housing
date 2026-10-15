"use client";

import { useRouter } from "next/navigation";
import { regionTitle, type RegionSummary } from "@/lib/api";
import { usePlaces } from "@/lib/places";
import Search from "@/components/Search";
import { COMPARE_COLORS } from "@/components/CompareChart";
import { compareHref, MAX_COMPARE } from "@/lib/compare";

/** The areas being compared, as removable chips, plus a search box to add one (up to four). */
export default function CompareControls({ regions }: { regions: Pick<RegionSummary, "id" | "kind" | "name" | "city" | "state">[] }) {
  const router = useRouter();
  const saved = usePlaces("saved");
  const ids = regions.map((r) => r.id);
  const go = (next: number[]) => router.push(compareHref(next), { scroll: false });

  return (
    <div className="flex flex-wrap items-center gap-2">
      {regions.map((r, i) => (
        <span key={r.id} className="inline-flex items-center gap-2 rounded-full border border-line bg-surface py-1 pl-3 pr-1 text-sm">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: COMPARE_COLORS[i] }} aria-hidden="true" />
          {regionTitle(r)}
          <button type="button" onClick={() => go(ids.filter((x) => x !== r.id))}
                  aria-label={`Remove ${regionTitle(r)}`} className="rounded-full px-2 text-muted hover:bg-surface-2 hover:text-ink">
            ×
          </button>
        </span>
      ))}
      {ids.length < MAX_COMPARE && (
        <div className="w-full sm:w-72">
          <Search compact shortcut={false} placeholder={ids.length ? "Add an area to compare" : "Search an area to compare"}
                  onSelect={(r) => !ids.includes(r.id) && go([...ids, r.id])} />
        </div>
      )}
      {ids.length === 0 && saved.length >= 2 && (
        <button type="button" onClick={() => go(saved.slice(0, MAX_COMPARE))} className="segment">
          Compare your saved places
        </button>
      )}
    </div>
  );
}
