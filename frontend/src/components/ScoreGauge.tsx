import { scoreRingColor } from "@/lib/format";

/**
 * Score dial. Deliberately an arc rather than a full ring: a full circle
 * implies a cycle, while this is a position on a fixed 0-100 scale, and the
 * open arc reads that way.
 */
export default function ScoreGauge({
  score,
  label,
  coverage,
  size = 168,
}: {
  score: number;
  label: string;
  coverage?: {
    metrics_used: number;
    metrics_total: number;
    missing_metrics: string[];
  };
  size?: number;
}) {
  const stroke = 8;
  const radius = (size - stroke * 2) / 2;
  const cx = size / 2;
  const cy = size / 2;

  // 240 degree arc, opening downward.
  const startAngle = 150;
  const sweep = 240;
  const toXY = (angle: number) => {
    const rad = (angle * Math.PI) / 180;
    return [cx + radius * Math.cos(rad), cy + radius * Math.sin(rad)];
  };
  const arcPath = (fromAngle: number, toAngle: number) => {
    const [x1, y1] = toXY(fromAngle);
    const [x2, y2] = toXY(toAngle);
    const large = toAngle - fromAngle > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${large} 1 ${x2} ${y2}`;
  };

  const clamped = Math.max(0, Math.min(100, score));
  const endAngle = startAngle + (sweep * clamped) / 100;
  const colour = scoreRingColor(score);
  const partial = coverage && coverage.metrics_used < coverage.metrics_total;

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size * 0.78 }}>
        <svg
          width={size}
          height={size}
          role="img"
          aria-label={`Growth Score ${score} out of 100, ${label}`}
        >
          <path
            d={arcPath(startAngle, startAngle + sweep)}
            fill="none"
            stroke="#dfe4ea"
            strokeWidth={stroke}
            strokeLinecap="round"
          />
          <path
            d={arcPath(startAngle, endAngle)}
            fill="none"
            stroke={colour}
            strokeWidth={stroke}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-x-0 top-[38%] flex flex-col items-center">
          <span className="tabular text-4xl font-medium leading-none text-ink">
            {score}
          </span>
          <span className="mt-1.5 text-sm" style={{ color: colour }}>
            {label}
          </span>
        </div>
      </div>

      {coverage && (
        <p
          className={`mt-1 text-xs ${partial ? "text-flag" : "text-ink-faint"}`}
          title={
            partial
              ? `No data for: ${coverage.missing_metrics.join(", ")}`
              : undefined
          }
        >
          Built from {coverage.metrics_used} of {coverage.metrics_total}{" "}
          indicators
        </p>
      )}
    </div>
  );
}
