"use client";

import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MetricSeries } from "@/lib/api";
import { formatValue, formatPct, INVERTED_METRICS } from "@/lib/format";

function movement(pct: number | null | undefined, inverted: boolean) {
  if (pct === null || pct === undefined) return "neutral" as const;
  if (Math.abs(pct) < 0.05) return "neutral" as const;
  const good = inverted ? pct < 0 : pct > 0;
  return good ? ("favourable" as const) : ("unfavourable" as const);
}

const TONE = {
  favourable: { hex: "#0e6e62", text: "text-favourable" },
  unfavourable: { hex: "#9e3b54", text: "text-unfavourable" },
  neutral: { hex: "#7b8794", text: "text-ink-faint" },
};

export default function MetricCard({ series }: { series: MetricSeries }) {
  const inverted = INVERTED_METRICS.has(series.metric_key);
  const tone = TONE[movement(series.change_3y_pct, inverted)];
  const gradientId = `grad-${series.metric_key}`;

  // When the exact three-year point was missing, the change was measured
  // from the nearest earlier observation. Say which year, rather than
  // calling a four-year change a three-year one.
  const threeYearLabel =
    series.baseline_3y_period !== null &&
    series.baseline_3y_period !== series.latest_period - 3
      ? `since ${series.baseline_3y_period}`
      : "3 yr";

  const countywide = series.label.includes("Countywide");

  return (
    <article className="border border-rule bg-surface">
      <div className="px-5 pt-4">
        <h3 className="text-sm text-ink-muted">
          {series.label.replace(" (Countywide)", "")}
        </h3>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="tabular text-[1.75rem] font-medium leading-none text-ink">
            {formatValue(series.latest_value, series.unit)}
          </span>
          <span className="tabular text-xs text-ink-faint">
            {series.latest_period}
          </span>
        </div>
        {countywide && (
          <span className="mt-2 inline-block text-xs text-ink-faint">
            Reported countywide
          </span>
        )}
      </div>

      <div className="mt-3 h-16">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={series.history}
            margin={{ top: 2, right: 0, bottom: 0, left: 0 }}
          >
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={tone.hex} stopOpacity={0.22} />
                <stop offset="100%" stopColor={tone.hex} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="period" hide />
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <Tooltip
              cursor={{ stroke: "#c4ccd6", strokeWidth: 1 }}
              contentStyle={{
                border: "1px solid #dfe4ea",
                borderRadius: 0,
                fontSize: 12,
                padding: "6px 8px",
                boxShadow: "none",
              }}
              labelStyle={{ color: "#8a99a8" }}
              formatter={(value) => [
                formatValue(
                  typeof value === "number" ? value : null,
                  series.unit,
                ),
                "",
              ]}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={tone.hex}
              strokeWidth={1.5}
              fill={`url(#${gradientId})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <dl className="flex divide-x divide-rule border-t border-rule text-sm">
        <div className="flex-1 px-5 py-2.5">
          <dt className="text-xs text-ink-faint">1 yr</dt>
          <dd
            className={`tabular ${TONE[movement(series.change_1y_pct, inverted)].text}`}
          >
            {formatPct(series.change_1y_pct)}
          </dd>
        </div>
        <div className="flex-1 px-5 py-2.5">
          <dt className="text-xs text-ink-faint">{threeYearLabel}</dt>
          <dd className={`tabular ${tone.text}`}>
            {formatPct(series.change_3y_pct)}
          </dd>
        </div>
      </dl>
    </article>
  );
}
