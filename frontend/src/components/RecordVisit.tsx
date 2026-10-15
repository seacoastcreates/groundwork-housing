"use client";

import { useEffect } from "react";
import { recordVisit } from "@/lib/places";

/** Adds the region being viewed to this browser's recently viewed list. Renders nothing. */
export default function RecordVisit({ id }: { id: number }) {
  useEffect(() => recordVisit(id), [id]);
  return null;
}
