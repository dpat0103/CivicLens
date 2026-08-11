export function formatValue(value: number | null | undefined, unit: string | null | undefined): string {
  if (value === null || value === undefined) return "\u2014";
  switch (unit) {
    case "$":
      return `$${Math.round(value).toLocaleString()}`;
    case "%":
      return `${value.toFixed(1)}%`;
    case "min":
      return `${Math.round(value)} min`;
    case "count":
      return Math.round(value).toLocaleString();
    case "per 1,000":
      return `${value.toFixed(1)} / 1,000`;
    case "index":
      return value.toFixed(1);
    default:
      return value.toLocaleString();
  }
}

export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "\u2014";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function scoreColor(score: number): string {
  if (score >= 75) return "text-emerald-600";
  if (score >= 60) return "text-emerald-500";
  if (score >= 40) return "text-amber-500";
  if (score >= 25) return "text-orange-500";
  return "text-red-500";
}

export function scoreRingColor(score: number): string {
  if (score >= 75) return "#059669";
  if (score >= 60) return "#10b981";
  if (score >= 40) return "#f59e0b";
  if (score >= 25) return "#f97316";
  return "#ef4444";
}

export function changeColor(pct: number | null | undefined, invert = false): string {
  if (pct === null || pct === undefined) return "text-slate-400";
  const positive = invert ? pct < 0 : pct > 0;
  if (pct === 0) return "text-slate-400";
  return positive ? "text-emerald-600" : "text-red-500";
}

export const CATEGORY_LABELS: Record<string, string> = {
  housing: "Housing",
  employment: "Employment",
  safety: "Safety",
  transportation: "Transportation",
  population: "Population",
};

// Metrics where a decrease is the positive direction (crime, unemployment, commute).
export const INVERTED_METRICS = new Set([
  "property_crime_rate",
  "violent_crime_rate",
  "unemployment_rate",
  "avg_commute_minutes",
]);
