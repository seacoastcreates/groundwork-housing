"use client";

import { usePathname } from "next/navigation";
import Search from "@/components/Search";

// The home page has its own large search box, so the header one is left out there.
export default function HeaderSearch() {
  if (usePathname() === "/") return null;
  return <Search compact />;
}
