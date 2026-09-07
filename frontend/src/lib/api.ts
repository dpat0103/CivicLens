/**
 * Typed client for the CivicLens API.
 *
 * The interfaces here mirror the Pydantic schemas in backend/app/schemas.py.
 * They are hand-maintained rather than generated, so a backend field rename
 * shows up as a runtime `undefined` rather than a compile error. The backend
 * test suite asserts the response shape against these names for that reason.
 *
 * The localhost fallback below is correct for local development and is a
 * deployment trap: a production build with NEXT_PUBLIC_API_URL unset will
 * try to reach the visitor's own machine, which fails in a way that looks
 * like the API is down rather than like a missing environment variable.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Location {
  id: number;
  fips: string;
  name: string;
  state: string;
  county: string | null;
  location_type: string;
  latitude: number | null;
  longitude: number | null;
}

export interface MetricPoint {
  period: number;
  value: number;
}

/**
 * How much of the Growth Score actually had data behind it.
 *
 * The score is renormalised over whatever weight contributed, so two
 * municipalities can share a score while being computed from different
 * numbers of indicators. Coverage is what makes that difference visible;
 * a score shown without it invites a comparison that isn't valid.
 */
export interface MetricCoverage {
  metrics_used: number;
  metrics_total: number;
  weight_covered: number;
  missing_metrics: string[];
}

export interface MetricSeries {
  category: string;
  metric_key: string;
  label: string;
  unit: string | null;
  latest_value: number;
  latest_period: number;
  change_1y_pct: number | null;
  change_3y_pct: number | null;
  change_5y_pct: number | null;
  baseline_1y_period: number | null;
  baseline_3y_period: number | null;
  baseline_5y_period: number | null;
  history: MetricPoint[];
  source: string | null;
}

export interface HeadlineChange {
  metric_key: string;
  label: string;
  change_3y_pct: number;
  baseline_period: number | null;
  latest_period: number | null;
}

export interface AreaReport {
  location: Location;
  growth_score: number;
  growth_score_label: string;
  metric_coverage: MetricCoverage;
  categories: Record<string, MetricSeries[]>;
  headline_changes: HeadlineChange[];
}

export interface CompareRow {
  location: Location;
  growth_score: number;
  metric_coverage: MetricCoverage;
  metrics: Record<string, number | null>;
}

export interface CompareResponse {
  metric_keys: string[];
  rows: CompareRow[];
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail || "Request failed", res.status);
  }
  return res.json();
}

async function post<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail || "Request failed", res.status);
  }
  return res.json();
}

export function searchLocations(q: string): Promise<Location[]> {
  const query = q ? `?q=${encodeURIComponent(q)}` : "";
  return request<Location[]>(`/locations${query}`);
}

export function listLocations(q?: string): Promise<Location[]> {
  const suffix = q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return request<Location[]>(`/locations${suffix}`);
}

export function getAreaReport(fips: string): Promise<AreaReport> {
  return request<AreaReport>(`/locations/${fips}/report`);
}

export function compareLocations(fipsList: string[]): Promise<CompareResponse> {
  const params = fipsList.map((f) => `fips=${encodeURIComponent(f)}`).join("&");
  return request<CompareResponse>(`/compare?${params}`);
}

export type AskIntent =
  | "lookup"
  | "compare"
  | "explanatory"
  | "methodology"
  | "unsupported";

/**
 * A record an answer drew on. `chunk_id` prefixes identify the path:
 * "sql:" for a direct database query, "fact:" for a generated municipal
 * summary, "meth:" for a hand-written methodology note.
 *
 * `provenance` is an array on direct queries (one entry per underlying row)
 * and a single string on retrieved chunks; see isSimulated() in format.ts.
 */
export interface Citation {
  chunk_id: string;
  kind: string;
  fips: string | null;
  location_name: string | null;
  category: string | null;
  metric_keys: string[];
  periods: number[];
  sources: string[];
  source_urls: string[];
  // Direct-query citations carry an array (one entry per row), retrieved
  // chunks carry a single resolved string.
  provenance: string | string[] | null;
  score: number | null;
}

export interface RetrievalTrace {
  used: boolean;
  chunks: string[];
  top_score: number | null;
  generator: string | null;
}

export interface ResolvedPlace {
  fips: string;
  name: string;
}

/**
 * `intent` is the important field. "lookup" and "compare" mean the figures
 * came from SQL with no model involved. "explanatory" and "methodology"
 * mean a model wrote the answer from the records in `citations`. The two
 * carry different confidence and the interface labels them differently.
 */
export interface AskResponse {
  question: string;
  intent: AskIntent;
  answer: string;
  grounded: boolean;
  citations: Citation[];
  resolved_places: ResolvedPlace[];
  provenance: string;
  suggestions: string[];
  retrieval: RetrievalTrace;
}

export interface CorpusStats {
  total_chunks: number;
  by_kind: Record<string, number>;
  embedding_provider: string[];
  pgvector_enabled: boolean;
}

export function askQuestion(question: string): Promise<AskResponse> {
  return post<AskResponse>("/ask", { question });
}

export function getCorpusStats(): Promise<CorpusStats> {
  return request<CorpusStats>("/ask/corpus");
}

export { ApiError, API_BASE };
