import type { CompareResponse } from "@/lib/api";
import { formatValue, INVERTED_METRICS } from "@/lib/format";

const METRIC_LABELS: Record<string, { label: string; unit: string | null }> = {
  median_rent: { label: "Median Rent", unit: "$" },
  population: { label: "Population", unit: "count" },
  employment: { label: "Employment", unit: "count" },
  unemployment_rate: { label: "Unemployment Rate", unit: "%" },
  median_household_income: { label: "Median Household Income", unit: "$" },
  new_housing_permits: { label: "New Housing Permits", unit: "count" },
  property_crime_rate: { label: "Property Crime Rate", unit: "per 1,000" },
  violent_crime_rate: { label: "Violent Crime Rate", unit: "per 1,000" },
  avg_commute_minutes: { label: "Average Commute", unit: "min" },
};

function bestIndex(values: (number | null)[], invert: boolean): number {
  let best = -1;
  let bestVal: number | null = null;
  values.forEach((v, i) => {
    if (v === null) return;
    if (bestVal === null || (invert ? v < bestVal : v > bestVal)) {
      bestVal = v;
      best = i;
    }
  });
  return best;
}

export default function CompareTable({ data }: { data: CompareResponse }) {
  const { metric_keys, rows } = data;

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            <th className="px-5 py-3 text-left font-medium text-slate-500">Metric</th>
            {rows.map((row) => (
              <th key={row.location.fips} className="px-5 py-3 text-left font-medium text-slate-900">
                {row.location.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-slate-100 bg-slate-50/50">
            <td className="px-5 py-3 font-medium text-slate-700">Growth Score</td>
            {rows.map((row) => (
              <td key={row.location.fips} className="px-5 py-3 font-semibold text-slate-900">
                {row.growth_score}
              </td>
            ))}
          </tr>
          {metric_keys.map((key) => {
            const meta = METRIC_LABELS[key] || { label: key, unit: null };
            const values = rows.map((r) => r.metrics[key] ?? null);
            const winner = bestIndex(values, INVERTED_METRICS.has(key));
            return (
              <tr key={key} className="border-b border-slate-100 last:border-0">
                <td className="px-5 py-3 text-slate-500">{meta.label}</td>
                {rows.map((row, i) => (
                  <td
                    key={row.location.fips}
                    className={`px-5 py-3 ${i === winner ? "font-semibold text-emerald-600" : "text-slate-700"}`}
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
