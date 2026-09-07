export function formatValue(
  value: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (value === null || value === undefined) return "\u2014";
  switch (unit) {
    case "$":
      return `$${Math.round(value).toLocaleString()}`;
    case "%":
      return `${value.toFixed(1)}%`;
    case "min":
      return `${Math.round(value)} min`;
    case "years":
      return `${value.toFixed(1)} yrs`;
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

// Score bands. Teal through rose rather than green through red: the pair
// stays distinguishable under the common colour-vision deficiencies, where
// green and red do not.
export function scoreRingColor(score: number): string {
  if (score >= 75) return "#0e6e62";
  if (score >= 60) return "#3f8b7d";
  if (score >= 40) return "#7b8794";
  if (score >= 25) return "#a86173";
  return "#9e3b54";
}

export function changeColor(
  pct: number | null | undefined,
  invert = false,
): string {
  if (pct === null || pct === undefined) return "text-ink-faint";
  if (Math.abs(pct) < 0.05) return "text-ink-faint";
  const favourable = invert ? pct < 0 : pct > 0;
  return favourable ? "text-favourable" : "text-unfavourable";
}

export const CATEGORY_LABELS: Record<string, string> = {
  population: "People and income",
  housing: "Housing",
  employment: "Work",
  transportation: "Getting around",
  safety: "Safety",
};

// Order categories so a report reads as an argument rather than an alphabet:
// who lives here, what housing costs, what work looks like, how people move.
export const CATEGORY_ORDER = [
  "population",
  "housing",
  "employment",
  "transportation",
  "safety",
];

// Metrics where a decrease is the desirable direction.
export const INVERTED_METRICS = new Set([
  "property_crime_rate",
  "violent_crime_rate",
  "unemployment_rate",
  "avg_commute_minutes",
  "poverty_rate",
  "rent_burden_pct",
  "vacancy_rate",
]);

// Short plain-language notes shown under a metric on request. Written for
// someone who has not read a Census methodology document.
export const METRIC_NOTES: Record<string, string> = {
  median_rent:
    "Median monthly gross rent, including utilities paid by the tenant.",
  median_home_value:
    "Median value of owner-occupied homes, as estimated by their owners.",
  rent_burden_pct:
    "Median share of household income going to rent. Above 30% is generally considered burdened.",
  homeownership_rate:
    "Share of occupied homes lived in by their owner rather than rented.",
  vacancy_rate: "Share of all housing units that are unoccupied.",
  median_household_income:
    "Midpoint of household income. Half of households earn more, half less.",
  per_capita_income:
    "Total income divided by every resident, including children.",
  poverty_rate:
    "Share of residents with income below the federal poverty threshold.",
  bachelors_or_higher_pct:
    "Share of adults 25 and over holding at least a bachelor's degree.",
  median_age: "Midpoint of resident ages.",
  population: "Total residents.",
  employment:
    "People employed across the whole county, not this municipality alone.",
  unemployment_rate:
    "Countywide share of the labour force actively seeking work.",
  avg_commute_minutes:
    "Mean one-way travel time to work for residents who commute.",
  transit_commute_pct:
    "Share of commuters travelling to work by public transport.",
};

// Which path produced an answer. Surfaced in the UI because "read from the
// database" and "written by a model from retrieved context" are different
// kinds of claim, and the user is entitled to know which one they got.
export const INTENT_LABELS: Record<string, string> = {
  lookup: "Database query",
  compare: "Database query",
  explanatory: "Retrieved and summarised",
  methodology: "Retrieved and summarised",
  unsupported: "Outside the dataset",
};

// Spelled out under the badge. The distinction between a figure read from
// a table and a sentence assembled from retrieved records is the whole
// point of the routing, and a two-word badge does not convey it.
export const INTENT_EXPLANATIONS: Record<string, string> = {
  lookup:
    "This figure was read straight from the database. No language model was involved, so the number cannot be invented.",
  compare:
    "These figures were read straight from the database. No language model was involved, so the numbers cannot be invented.",
  explanatory:
    "This answer was assembled from indexed records, listed below. Nothing outside those records was used.",
  methodology:
    "This answer was assembled from the methodology notes, listed below.",
  unsupported: "Nothing in the dataset answers this.",
};

export function intentTone(intent: string): string {
  switch (intent) {
    case "lookup":
    case "compare":
      return "border-favourable/40 bg-favourable/10 text-favourable";
    case "explanatory":
    case "methodology":
      return "border-accent/30 bg-accent-soft text-accent";
    default:
      return "border-rule bg-paper text-ink-faint";
  }
}

// A citation's provenance is an array on direct queries and a string on
// retrieved chunks. Collapse both to one answer: is any of it simulated?
export function isSimulated(
  provenance: string | string[] | null | undefined,
): boolean {
  if (!provenance) return false;
  return Array.isArray(provenance)
    ? provenance.includes("simulated")
    : provenance === "simulated";
}

export function metricKeyLabel(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
