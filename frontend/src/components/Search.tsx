"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { usd, type RegionSummary } from "@/lib/api";
import { Delta } from "@/components/ui";

export default function Search({ autoFocus = false, compact = false, onSelect, placeholder, shortcut = true }: {
  autoFocus?: boolean;
  compact?: boolean;
  /** Called with the chosen region instead of navigating to its page. */
  onSelect?: (r: RegionSummary) => void;
  placeholder?: string;
  /** Whether "/" focuses this box. */
  shortcut?: boolean;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<RegionSummary[]>([]);
  // The query the current items answer, so "No matches" only shows once a search has come back.
  const [answered, setAnswered] = useState("");
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) return;
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(term)}`, { signal: ctrl.signal })
        .then((r) => (r.ok ? r.json() : []))
        .then((rows: RegionSummary[]) => {
          setItems(rows);
          setAnswered(term);
          setActive(0);
        })
        .catch(() => {});
    }, 150);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);

  // "/" focuses search from anywhere on the page, unless the user is already typing somewhere.
  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return;
      // Several search boxes can be mounted; only the visible one takes the shortcut.
      if (!input.current || input.current.offsetParent === null) return;
      e.preventDefault();
      input.current.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shortcut]);

  useEffect(() => {
    const onDown = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, []);

  const term = q.trim();
  // Results for a query that has since been cleared are hidden rather than reset inside the effect.
  const shown = term.length >= 2 ? items : [];
  const noMatches = term.length >= 2 && answered === term && items.length === 0;
  const expanded = open && (shown.length > 0 || noMatches);

  const go = (r: RegionSummary) => {
    setQ("");
    setItems([]);
    setOpen(false);
    if (onSelect) onSelect(r);
    else {
      input.current?.blur();
      router.push(`/regions/${r.id}`);
    }
  };

  return (
    <div ref={root} className={`relative w-full ${compact ? "sm:max-w-xs" : "max-w-md"}`}>
      <input
        ref={input}
        type="search"
        value={q}
        autoFocus={autoFocus}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setActive((a) => Math.min(a + 1, shown.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && expanded && shown[active]) go(shown[active]);
          else if (e.key === "Escape") {
            if (expanded) setOpen(false);
            else input.current?.blur();
          }
        }}
        placeholder={placeholder ?? (compact ? "Search ZIP, city, metro" : "Search a ZIP, city or metro")}
        aria-label="Search a ZIP, city or metro"
        aria-keyshortcuts={shortcut ? "/" : undefined}
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-activedescendant={expanded && shown[active] ? `${listId}-${active}` : undefined}
        className={`w-full rounded-lg border border-line bg-surface pr-9 shadow-sm outline-none focus:border-accent ${
          compact ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-base"
        }`}
      />
      {q === "" && shortcut && (
        <kbd
          aria-hidden="true"
          className="pointer-events-none absolute right-2.5 top-1/2 hidden sm:block -translate-y-1/2 rounded border border-line px-1.5 text-xs text-muted"
        >
          /
        </kbd>
      )}
      {expanded && (
        <ul id={listId} role="listbox" className="card absolute z-20 mt-1 max-h-96 w-full min-w-72 overflow-auto py-1">
          {noMatches && (
            <li className="px-4 py-3 text-sm text-ink-2" role="presentation">
              No matches for “{term}”. Try a 5-digit ZIP, a city or a metro name.
            </li>
          )}
          {shown.map((r, i) => (
            <li key={r.id} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
              <button
                tabIndex={-1}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(r)}
                className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm ${i === active ? "bg-surface-2" : ""}`}
              >
                <span className="min-w-0">
                  <span className="block truncate">
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
                </span>
                <span className="shrink-0 text-right text-xs">
                  <span className="block tabular text-ink">{usd(r.value)}</span>
                  <span className="text-muted">next 12 mo </span>
                  <Delta v={r.change_pct} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
