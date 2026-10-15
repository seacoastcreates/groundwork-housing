"use client";

import { useMemo, useState } from "react";
import type { RegionSummary } from "@/lib/api";
import { RegionTable, type HeaderSort, type SortCol, type SortDir } from "@/components/ui";

const COLLAPSED_ROWS = 15;

const KEYS: Record<SortCol, (r: RegionSummary) => number | string | null> = {
  area: (r) => r.name,
  value: (r) => r.value,
  change_1y: (r) => r.change_1y_pct,
  forecast: (r) => r.change_pct,
  rank: (r) => r.relative_pct,
};

// Columns whose natural first click is ascending (names); the rest start strongest-first.
const FIRST_DIR: Record<SortCol, SortDir> = { area: "asc", value: "desc", change_1y: "desc", forecast: "desc", rank: "desc" };

/** A metro's ZIP codes: filter by ZIP or town, sort by any column, first rows only until expanded. */
export default function ZipExplorer({ rows, metroName }: { rows: RegionSummary[]; metroName: string }) {
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<{ col: SortCol; dir: SortDir }>({ col: "rank", dir: "desc" });
  const [expanded, setExpanded] = useState(false);

  const matching = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const hits = f
      ? rows.filter((r) => r.name.startsWith(f) || r.city?.toLowerCase().includes(f) || r.county?.toLowerCase().includes(f))
      : rows;
    const key = KEYS[sort.col];
    const sign = sort.dir === "asc" ? 1 : -1;
    // Missing values sort last in either direction.
    return [...hits].sort((a, b) => {
      const x = key(a), y = key(b);
      if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
      return (typeof x === "string" ? x.localeCompare(y as string) : x - (y as number)) * sign;
    });
  }, [rows, filter, sort]);

  const filtering = filter.trim() !== "";
  const showAll = expanded || filtering;
  const shown = showAll ? matching : matching.slice(0, COLLAPSED_ROWS);

  const sorts = Object.fromEntries(
    (Object.keys(KEYS) as SortCol[]).map((col): [SortCol, HeaderSort] => [
      col,
      {
        dir: sort.col === col ? sort.dir : null,
        onClick: () =>
          setSort((s) => (s.col === col ? { col, dir: s.dir === "asc" ? "desc" : "asc" } : { col, dir: FIRST_DIR[col] })),
      },
    ]),
  );

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <input
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={`Filter ZIPs or towns in ${metroName.split(",")[0]}`}
          aria-label="Filter ZIP codes"
          className="w-full max-w-sm rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-sm outline-none focus:border-accent"
        />
        <span className="text-sm text-ink-2" aria-live="polite">
          {filtering ? `${matching.length} of ${rows.length} ZIPs match` : `${rows.length} ZIPs · click a column to sort`}
        </span>
      </div>
      <div className={`card overflow-x-auto ${showAll ? "max-h-[75vh] overflow-y-auto" : ""}`}>
        <RegionTable rows={shown} showRank sorts={sorts} stickyHeader={showAll} />
        {matching.length === 0 && (
          <p className="px-4 py-6 text-center text-sm text-ink-2">No ZIPs in this metro match “{filter.trim()}”.</p>
        )}
      </div>
      {!filtering && rows.length > COLLAPSED_ROWS && (
        <button type="button" onClick={() => setExpanded((e) => !e)} className="segment mt-3">
          {expanded ? `Show top ${COLLAPSED_ROWS} only` : `Show all ${rows.length} ZIPs`}
        </button>
      )}
    </>
  );
}
