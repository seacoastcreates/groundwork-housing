import "server-only";
import { geoAlbersUsa, geoMercator, geoPath } from "d3-geo";
import { feature, mesh } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import statesAlbers from "us-atlas/states-albers-10m.json";
import states10m from "us-atlas/states-10m.json";
import type { MapPoint } from "@/lib/api";

// Projection and path geometry are computed on the server, so the browser gets SVG path strings and
// x/y positions rather than the atlas files and d3.

/** What the browser needs for one dot: no coordinates, and numbers rounded to keep the page small. */
export type PlacedPoint = Omit<MapPoint, "lat" | "lon"> & { x: number; y: number };
export type MapLayout = { width: number; height: number; land: string; borders: string; points: PlacedPoint[] };

type States = Topology<{ states: GeometryCollection; nation: GeometryCollection }>;

/** Every metro on the US in Albers USA (Alaska and Hawaii inset), matching us-atlas's pre-projected states. */
export function nationLayout(points: MapPoint[]): MapLayout {
  const us = statesAlbers as unknown as States;
  // us-atlas's albers files are projected with exactly this projection into a 975 x 610 frame.
  const projection = geoAlbersUsa().scale(1300).translate([487.5, 305]);
  const path = geoPath().digits(1);   // a tenth of a pixel is plenty, and keeps the page small
  return {
    width: 975,
    height: 610,
    land: path(feature(us, us.objects.nation)) ?? "",
    borders: path(mesh(us, us.objects.states, (a, b) => a !== b)) ?? "",
    points: place(points, (lon, lat) => projection([lon, lat])),
  };
}

/** One metro's ZIPs, fitted to the frame, with state outlines for context. */
export function metroLayout(points: MapPoint[], width = 800, height = 520): MapLayout | null {
  if (points.length < 3) return null;
  const us = states10m as unknown as States;
  const pad = 16;
  const projection = geoMercator()
    .fitExtent([[pad, pad], [width - pad, height - pad]], {
      type: "MultiPoint",
      coordinates: points.map((p) => [p.lon, p.lat]),
    })
    .clipExtent([[0, 0], [width, height]]);
  const path = geoPath(projection).digits(1);
  return {
    width,
    height,
    land: path(feature(us, us.objects.nation)) ?? "",
    borders: path(mesh(us, us.objects.states, (a, b) => a !== b)) ?? "",
    points: place(points, (lon, lat) => projection([lon, lat])),
  };
}

const round = (v: number | null, digits = 1) => (v == null ? null : Math.round(v * 10 ** digits) / 10 ** digits);

function place(points: MapPoint[], project: (lon: number, lat: number) => [number, number] | null): PlacedPoint[] {
  const out: PlacedPoint[] = [];
  for (const { lat, lon, ...p } of points) {
    const xy = project(lon, lat);
    if (!xy) continue;
    out.push({
      ...p, x: round(xy[0])!, y: round(xy[1])!, value: round(p.value, 0), change_pct: round(p.change_pct, 2),
      change_1y_pct: round(p.change_1y_pct, 2), relative_rank_pct: round(p.relative_rank_pct, 0),
    });
  }
  return out;
}
