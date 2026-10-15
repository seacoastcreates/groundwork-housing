const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type RegionSummary = {
  id: number;
  kind: "country" | "msa" | "zip";
  name: string;
  state: string | null;
  city: string | null;
  county: string | null;
  metro_id: number | null;
  metro_name: string | null;
  size_rank: number;
  value: number | null;
  change_1y_pct: number | null;
  change_5y_pct: number | null;
  change_pct: number | null;
  low_pct: number | null;
  high_pct: number | null;
  trend_pct: number | null;
  relative_pct: number | null;
  relative_rank_pct: number | null;
};

export type RegionList = { total: number; items: RegionSummary[] };

export type MapPoint = Pick<RegionSummary, "id" | "kind" | "name" | "city" | "state" | "size_rank" | "value"
  | "change_1y_pct" | "change_pct" | "relative_rank_pct"> & { lat: number; lon: number };

export type HeatPoint = {
  month: string;
  months_of_supply: number | null;
  median_dom: number | null;
  sale_to_list: number | null;
  price_drops: number | null;
};

export type RegionDetail = {
  region: RegionSummary;
  history: { month: string; value: number }[];
  origin: string | null;
  forecast_month: string | null;
  heat: HeatPoint[];
  zillow_forecast: { target: string; growth_pct: number }[];
  zillow_base: string | null;
  rent: { month: string; rent: number; change_1y_pct: number | null; source: "own" | "metro" } | null;
  /** Absent from responses cached before the track record existed. */
  track_record?: PastForecast[];
};

export type PastForecast = {
  origin: string;
  target: string;
  predicted_pct: number;
  low_pct: number;
  high_pct: number;
  actual_pct: number;
};

export type TrackRecordRow = {
  period: string;
  level: "metro" | "zip";
  n: number;
  mae: number;
  bias: number;
  coverage_pct: number;
  direction_pct: number;
};

export type TrackRecord = { rows: TrackRecordRow[]; first_origin: string | null; last_origin: string | null };

export type Overview = {
  nation: RegionSummary;
  model_version: string | null;
  origin: string | null;
  horizon_months: number | null;
  mortgage_rate: number | null;
  mortgage_rate_1y_ago: number | null;
  counts: Record<string, number>;
  sources: string;
};

export type LevelMetrics = {
  mae: number;
  bias: number;
  mae_recent: number;
  rank_ic: number | null;
  top_decile_beat: number | null;
  decile_spread: number | null;
  by_year: Record<string, number>;
};

export type ModelInfo = {
  model_version: string;
  trained_at: string;
  origin: string;
  horizon: number;
  metrics: {
    horizon_months: number;
    origin: string;
    redfin_lag_months: number;
    test_years: [number, number];
    interval?: Record<"metro" | "zip", [number, number]>;
    backtest?: Record<"metro" | "zip" | "relative", Record<string, LevelMetrics>>;
    config?: {
      trend_groups: string[];
      relative_groups: string[];
      trend_params: Record<string, number | string>;
      relative_params: Record<string, number | string>;
      national?: { method: "aggregate" | "own_row"; weighting: string; rural_parent: string; override?: boolean };
    };
    ablation?: Partial<Record<"trend" | "relative" | "relative_round2" | "trend_retest" | "relative_retest", AblationReport>>;
    national?: NationalReport;
    tuning?: Partial<Record<"trend" | "relative", TuningReport>>;
  };
};

export type AblationRun = {
  groups: string[];
  mae: number;
  mae_recent: number;
  rank_ic: number;
  top_decile_beat?: number;
  passes?: boolean;
  years_better?: number;
  years_active?: number;
};
export type NationalReport = {
  fidelity_2005_2016: Record<string, { mae: number; bias: number }>;
  weighting: string;
  backtest: Record<"aggregate" | "own_row" | "damped", { mae: number; bias: number; by_year: Record<string, number> }>;
  years_better: number;
  adopt: boolean;
};

export type AblationReport = { baseline: AblationRun; variants: Record<string, AblationRun>; adopted: string[] };

type HoldoutScore = { mae: number; rank_ic: number; by_year: Record<string, { mae: number; rank_ic: number }> };
export type TuningReport = {
  tune_years: number[];
  holdout_years: number[];
  trials: Record<string, number>;
  best_params: Record<string, number | string>;
  param_importance: Record<string, number>;
  holdout: { default: HoldoutScore; tuned: HoldoutScore; adopt: boolean };
};

async function get<T>(path: string, revalidate = 3600): Promise<T | null> {
  const res = await fetch(`${API_URL}/api/v1${path}`, { next: { revalidate } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json();
}

function qs(params: Record<string, string | number | undefined | null>) {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== "") s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
}

export const api = {
  overview: () => get<Overview>("/overview"),
  metros: (p: { sort?: string; limit?: number; offset?: number; state?: string } = {}) =>
    get<RegionList>(`/metros${qs(p)}`),
  zips: (p: { metro_id?: number; sort?: string; limit?: number; offset?: number; max_size_rank?: number } = {}) =>
    get<RegionList>(`/zips${qs(p)}`),
  region: (id: number | string) => get<RegionDetail>(`/regions/${id}`),
  model: () => get<ModelInfo>("/model"),
  trackRecord: () => get<TrackRecord>("/track-record"),
  map: (metroId?: number) => get<MapPoint[]>(`/map${qs({ metro_id: metroId })}`),
};

export const usd = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const usdShort = (v: number) =>
  v >= 1e6 ? `$${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1)}M` : `$${Math.round(v / 1000)}K`;

export const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}%`;

/** Dollar change implied by a percent change on a value, e.g. "+$8,500" (or "+$33K" when short). */
export function usdChange(value: number | null | undefined, changePct: number | null | undefined, short = false) {
  if (value == null || changePct == null) return "—";
  const d = (value * changePct) / 100;
  const sign = d >= 50 ? "+" : d <= -50 ? "−" : "";
  const abs = Math.abs(d);
  const body = short && abs >= 1000 ? usdShort(abs) : `$${(Math.round(abs / 100) * 100).toLocaleString("en-US")}`;
  return `${sign}${body}`;
}

export const monthLabel = (iso: string, short = false) =>
  new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", {
    month: short ? "short" : "long",
    year: "numeric",
  });

export function regionTitle(r: Pick<RegionSummary, "kind" | "name" | "city" | "state">) {
  if (r.kind === "zip") return `${r.name} · ${r.city ?? ""}${r.state ? `, ${r.state}` : ""}`;
  return r.name;
}
