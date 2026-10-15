"use client";

import { useSyncExternalStore } from "react";

// Saved and recently viewed places live in this browser only (localStorage), as lists of region IDs.
// Storage can be unavailable (private windows, blocked site data), so every access is guarded and the
// lists simply come back empty.
const KEYS = { saved: "groundwork:saved", recent: "groundwork:recent" } as const;
export const MAX_SAVED = 50;
export const MAX_RECENT = 8;
type List = keyof typeof KEYS;

const EMPTY: number[] = [];
const cache: Partial<Record<List, { raw: string | null; ids: number[] }>> = {};
const listeners = new Set<() => void>();

function read(list: List): number[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(KEYS[list]);
  } catch {}
  // Same raw string, same array: useSyncExternalStore needs a stable snapshot.
  const hit = cache[list];
  if (hit && hit.raw === raw) return hit.ids;
  let ids = EMPTY;
  try {
    const parsed = raw ? JSON.parse(raw) : [];
    if (Array.isArray(parsed)) ids = parsed.filter((n): n is number => Number.isInteger(n));
  } catch {}
  cache[list] = { raw, ids };
  return ids;
}

function write(list: List, ids: number[]) {
  try {
    localStorage.setItem(KEYS[list], JSON.stringify(ids));
  } catch {}
  listeners.forEach((l) => l());
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  // Other tabs.
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || Object.values(KEYS).includes(e.key as (typeof KEYS)[List])) onChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function usePlaces(list: List): number[] {
  return useSyncExternalStore(subscribe, () => read(list), () => EMPTY);
}

export function toggleSaved(id: number) {
  const ids = read("saved");
  write("saved", ids.includes(id) ? ids.filter((x) => x !== id) : [id, ...ids].slice(0, MAX_SAVED));
}

export function recordVisit(id: number) {
  const ids = read("recent");
  if (ids[0] === id) return;
  write("recent", [id, ...ids.filter((x) => x !== id)].slice(0, MAX_RECENT));
}

export function clearList(list: List) {
  write(list, []);
}
