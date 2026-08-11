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
  history: MetricPoint[];
  source: string | null;
}

export interface AreaReport {
  location: Location;
  growth_score: number;
  growth_score_label: string;
  categories: Record<string, MetricSeries[]>;
  headline_changes: string[];
}

export interface CompareRow {
  location: Location;
  growth_score: number;
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

export function searchLocations(q: string): Promise<Location[]> {
  const query = q ? `?q=${encodeURIComponent(q)}` : "";
  return request<Location[]>(`/locations${query}`);
}

export function listLocations(): Promise<Location[]> {
  return request<Location[]>("/locations");
}

export function getAreaReport(fips: string): Promise<AreaReport> {
  return request<AreaReport>(`/locations/${fips}/report`);
}

export function compareLocations(fipsList: string[]): Promise<CompareResponse> {
  const params = fipsList.map((f) => `fips=${encodeURIComponent(f)}`).join("&");
  return request<CompareResponse>(`/compare?${params}`);
}

export { ApiError, API_BASE };
