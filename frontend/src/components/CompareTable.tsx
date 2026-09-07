import type { CompareResponse } from "@/lib/api";
import { formatValue, INVERTED_METRICS, METRIC_NOTES } from "@/lib/format";

const METRIC_META: Record<string, { label: string; unit: string | null }> = {
  population: { label: "Population", unit: "count" },
  median_age: { label: "Median age", unit: "years" },
  median_household_income: { label: "Median household income", unit: "$" },
  per_capita_income: { label: "Per capita income", unit: "$" },
  poverty_rate: { label: "Poverty rate", unit: "%" },
  bachelors_or_higher_pct: { label: "Bachelor's or higher", unit: "%" },
  median_rent: { label: "Median rent", unit: "$" },
  median_home_value: { label: "Median home value", unit: "$" },
  rent_burden_pct: { label: "Rent as share of income", unit: "%" },
  homeownership_rate: { label: "Homeownership rate", unit: "%" },
  vacancy_rate: { label: "Vacancy rate", unit: "%" },
  employment: { label: "Employment (countywide)", unit: "count" },
  unemployment_rate: { label: "Unemployment (countywide)", unit: "%" },
  avg_commute_minutes: { label: "Average commute", unit: "min" },
  transit_commute_pct: { label: "Commute by transit", unit: "%" },
  new_housing_permits: { label: "New housing permits", unit: "count" },
  property_crime_rate: { label: "Property crime", unit: "per 1,000" },
  violent_crime_rate: { label: "Violent crime", unit: "per 1,000" },
};

function leadingIndex(values: (number | null)[], invert: boolean): number {
  let best = -1;
  let bestVal: number | null = null;
  values.forEach((v, i) => {
    if (v === null) return;
    if (bestVal === null || (invert ? v < bestVal : v > bestVal)) {
      bestVal = v;
      best = i;
    }
  });
  // Nothing leads if every municipality reports the same figure, which is
  // the normal case for countywide metrics within one county.
  const present = values.filter((v) => v !== null);
  if (present.length > 1 && new Set(present).size === 1) return -1;
  return best;
}

export default function CompareTable({ data }: { data: CompareResponse }) {
  const { metric_keys, rows } = data;

  return (
    <div className="overflow-x-auto border border-rule bg-surface">
      <table className="w-full min-w-[680px] border-collapse text-sm">
        <caption className="sr-only">
          Indicators compared across selected municipalities
        </caption>
        <thead>
          <tr className="border-b border-rule-strong">
            <th
              scope="col"
              className="px-5 py-3 text-left font-medium text-ink-faint"
            >
              Indicator
            </th>
            {rows.map((row) => (
              <th
                key={row.location.fips}
                scope="col"
                className="px-5 py-3 text-left font-medium text-ink"
              >
                {row.location.name}
                <span className="block text-xs font-normal text-ink-faint">
                  {row.location.county}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-rule bg-accent-soft/40">
            <th
              scope="row"
              className="px-5 py-3 text-left font-medium text-ink"
            >
              Growth Score
            </th>
            {rows.map((row) => (
              <td key={row.location.fips} className="px-5 py-3">
                <span className="tabular font-medium text-ink">
                  {row.growth_score}
                </span>
                <span className="ml-2 text-xs text-ink-faint">
                  {row.metric_coverage.metrics_used}/
                  {row.metric_coverage.metrics_total}
                </span>
              </td>
            ))}
          </tr>

          {metric_keys.map((key) => {
            const meta = METRIC_META[key] ?? { label: key, unit: null };
            const values = rows.map((r) => r.metrics[key] ?? null);
            const leader = leadingIndex(values, INVERTED_METRICS.has(key));
            return (
              <tr key={key} className="border-b border-rule last:border-0">
                <th
                  scope="row"
                  className="px-5 py-3 text-left font-normal text-ink-muted"
                  title={METRIC_NOTES[key]}
                >
                  {meta.label}
                </th>
                {rows.map((row, i) => (
                  <td
                    key={row.location.fips}
                    className={`tabular px-5 py-3 ${
                      i === leader ? "font-medium text-favourable" : "text-ink"
                    }`}
                  >
                    {formatValue(row.metrics[key], meta.unit)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
