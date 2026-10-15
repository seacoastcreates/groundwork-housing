"use client";

import { toggleSaved, usePlaces } from "@/lib/places";

export function Star({ filled }: { filled: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"
         fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8l-5.4 2.9 1.1-6.1-4.5-4.2 6.1-.8z" />
    </svg>
  );
}

/** Star toggle that saves a region to this browser's "Your places" list. */
export default function SaveButton({ id, name, compact = false }: { id: number; name: string; compact?: boolean }) {
  const saved = usePlaces("saved").includes(id);
  return (
    <button
      type="button"
      onClick={() => toggleSaved(id)}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${name} from your places` : `Save ${name} to your places`}
      title={saved ? "Saved. Click to remove" : "Save to your places"}
      className={compact
        ? `rounded p-1 ${saved ? "text-brick" : "text-muted hover:text-ink"}`
        : `segment inline-flex items-center gap-2 ${saved ? "border-brick text-brick" : ""}`}
    >
      <Star filled={saved} />
      {!compact && (saved ? "Saved" : "Save")}
    </button>
  );
}
