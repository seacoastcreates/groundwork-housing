"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import type { RegionSummary } from "@/lib/api";

export default function Search({ autoFocus = false }: { autoFocus?: boolean }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<RegionSummary[]>([]);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const listId = useId();

  useEffect(() => {
    if (q.trim().length < 2) return;
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(q.trim())}`, { signal: ctrl.signal })
        .then((r) => (r.ok ? r.json() : []))
        .then((rows: RegionSummary[]) => {
          setItems(rows);
          setActive(0);
        })
        .catch(() => {});
    }, 150);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);

  // Results for a query that has since been cleared are hidden rather than reset inside the effect.
  const shown = q.trim().length >= 2 ? items : [];

  const go = (r: RegionSummary) => {
    setQ("");
    setItems([]);
    router.push(`/regions/${r.id}`);
  };

  return (
    <div className="relative w-full max-w-md">
      <input
        type="search"
        value={q}
        autoFocus={autoFocus}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, shown.length - 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter" && shown[active]) go(shown[active]);
        }}
        placeholder="Search a ZIP, city or metro"
        aria-label="Search a ZIP, city or metro"
        role="combobox"
        aria-expanded={shown.length > 0}
        aria-controls={listId}
        className="w-full rounded-lg border border-line bg-surface px-4 py-2.5 text-base shadow-sm outline-none focus:border-accent"
      />
      {shown.length > 0 && (
        <ul id={listId} role="listbox" className="card absolute z-20 mt-1 max-h-80 w-full overflow-auto py-1">
          {shown.map((r, i) => (
            <li key={r.id} role="option" aria-selected={i === active}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => go(r)}
                className={`flex w-full items-baseline justify-between gap-3 px-4 py-2 text-left text-sm ${i === active ? "bg-surface-2" : ""}`}
              >
                <span>
                  {r.kind === "zip" ? (
                    <>
                      <span className="tabular font-medium">{r.name}</span>{" "}
                      <span className="text-ink-2">{r.city}, {r.state}</span>
                    </>
                  ) : (
                    <span className="font-medium">{r.name}</span>
                  )}
                </span>
                <span className="text-xs text-muted">{r.kind === "zip" ? "ZIP" : "Metro"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
