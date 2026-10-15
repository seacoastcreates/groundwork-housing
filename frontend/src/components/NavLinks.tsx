"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Markets", match: (p: string) => p === "/" || p.startsWith("/regions") },
  { href: "/compare", label: "Compare", match: (p: string) => p.startsWith("/compare") },
  { href: "/track-record", label: "Track record", match: (p: string) => p.startsWith("/track-record") },
  { href: "/model", label: "How it works", match: (p: string) => p.startsWith("/model") },
];

export default function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-6 text-sm" aria-label="Main">
      {LINKS.map((l) => {
        const active = l.match(pathname);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={`border-b-2 py-1 ${active ? "border-accent font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink"}`}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
