"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { STATES } from "@/lib/states";

export default function StateFilter({ value }: { value: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  return (
    <label className="flex items-center gap-2 text-sm text-ink-2">
      State
      <select
        value={value ?? ""}
        onChange={(e) => {
          const next = new URLSearchParams(params);
          if (e.target.value) next.set("state", e.target.value);
          else next.delete("state");
          next.delete("n");
          const q = next.toString();
          router.push(q ? `${pathname}?${q}` : pathname, { scroll: false });
        }}
        className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-accent"
      >
        <option value="">All states</option>
        {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
    </label>
  );
}
