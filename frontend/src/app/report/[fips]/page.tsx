import Link from "next/link";
import { notFound } from "next/navigation";
import ScoreGauge from "@/components/ScoreGauge";
import MetricCard from "@/components/MetricCard";
import AskPanel from "@/components/AskPanel";
import { getAreaReport, ApiError } from "@/lib/api";
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  formatPct,
  INVERTED_METRICS,
} from "@/lib/format";

export default async function ReportPage({
  params,
}: PageProps<"/report/[fips]">) {
  const { fips } = await params;

  let report;
  try {
    report = await getAreaReport(fips);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    return (
      <main className="mx-auto max-w-6xl px-6 py-16">
        <div className="max-w-xl border-l-2 border-unfavourable bg-surface px-4 py-3">
          <p className="text-ink">
            The CivicLens API isn&rsquo;t responding. Start the backend on port
            8000, then reload.
          </p>
        </div>
      </main>
    );
  }

  const {
    location,
    growth_score,
    growth_score_label,
    metric_coverage,
    categories,
    headline_changes,
  } = report;

  const simulated = Object.values(categories)
    .flat()
    .some((s) => s.source?.toLowerCase().includes("seed"));

  return (
    <main>
      <section className="border-b border-rule bg-surface">
        <div className="mx-auto max-w-6xl px-6 pb-10 pt-10">
          <nav className="text-sm text-ink-faint">
            <Link
              href="/places"
              className="transition-colors hover:text-accent"
            >
              Municipalities
            </Link>
            <span className="px-2">/</span>
            <span>{location.county} County</span>
          </nav>

          <div className="mt-4 flex flex-wrap items-end justify-between gap-8">
            <div>
              <h1 className="serif text-4xl tracking-tight text-ink">
                {location.name}
              </h1>
              <p className="mt-1 text-ink-muted">
                {location.county} County, New Jersey
              </p>
              {simulated && (
                <p className="mt-3 inline-block bg-flag-soft px-2 py-1 text-xs text-flag">
                  Some indicators here are demonstration data, not measured
                </p>
              )}
            </div>

            <ScoreGauge
              score={growth_score}
              label={growth_score_label}
              coverage={metric_coverage}
            />
          </div>
        </div>
      </section>

      {headline_changes.length > 0 && (
        <section className="border-b border-rule bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-6">
            <h2 className="text-sm text-ink-faint">
              Largest movements over three years
            </h2>
            <ul className="mt-3 flex flex-wrap gap-x-10 gap-y-3">
              {headline_changes.slice(0, 4).map((change) => {
                const inverted = INVERTED_METRICS.has(change.metric_key);
                const pct = change.change_3y_pct;
                const favourable =
                  pct === null ? null : inverted ? pct < 0 : pct > 0;
                return (
                  <li
                    key={change.metric_key}
                    className="flex items-baseline gap-2"
                  >
                    <span className="text-sm text-ink-muted">
                      {change.label}
                    </span>
                    <span
                      className={`tabular text-sm ${
                        favourable === null
                          ? "text-ink-faint"
                          : favourable
                            ? "text-favourable"
                            : "text-unfavourable"
                      }`}
                    >
                      {formatPct(pct)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      )}

      <div className="mx-auto max-w-6xl px-6 py-12">
        {CATEGORY_ORDER.filter((cat) => categories[cat]?.length).map((cat) => (
          <section key={cat} className="mb-12">
            <h2 className="serif border-b border-rule pb-2 text-xl text-ink">
              {CATEGORY_LABELS[cat] ?? cat}
            </h2>
            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {categories[cat].map((series) => (
                <MetricCard key={series.metric_key} series={series} />
              ))}
            </div>
          </section>
        ))}

        <section className="mt-4">
          <AskPanel locationName={location.name} />
        </section>

        <p className="mt-10 max-w-[68ch] text-sm leading-relaxed text-ink-faint">
          Figures are survey estimates covering a five-year window and carry
          margins of error that widen for smaller municipalities.{" "}
          <Link
            href="/about"
            className="text-accent underline underline-offset-4"
          >
            How these numbers are put together
          </Link>
        </p>
      </div>
    </main>
  );
}
