"use client";

import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";
import type { MetricSeries } from "@/lib/api";
import { formatValue, formatPct, changeColor, INVERTED_METRICS } from "@/lib/format";

export default function MetricCard({ series }: { series: MetricSeries }) {
  const inverted = INVERTED_METRICS.has(series.metric_key);
  const chartColor = (() => {
    const pct = series.change_3y_pct;
    if (pct === null || pct === undefined || pct === 0) return "#94a3b8";
    const positive = inverted ? pct < 0 : pct > 0;
    return positive ? "#059669" : "#ef4444";
  })();

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-slate-500">{series.label}</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">
            {formatValue(series.latest_value, series.unit)}
          </div>
        </div>
        <div className="h-12 w-24 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series.history}>
              <YAxis hide domain={["dataMin", "dataMax"]} />
              <Line
                type="monotone"
                dataKey="value"
                stroke={chartColor}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-4 flex gap-4 border-t border-slate-100 pt-3 text-sm">
        <div>
          <span className="text-slate-400">1yr </span>
          <span className={changeColor(series.change_1y_pct, inverted)}>
            {formatPct(series.change_1y_pct)}
          </span>
        </div>
        <div>
          <span className="text-slate-400">3yr </span>
          <span className={changeColor(series.change_3y_pct, inverted)}>
            {formatPct(series.change_3y_pct)}
          </span>
        </div>
      </div>
      {series.source && (
        <div className="mt-2 text-xs text-slate-300">Source: {series.source}</div>
      )}
    </div>
  );
}
