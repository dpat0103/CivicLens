import Link from "next/link";
import { notFound } from "next/navigation";
import ScoreGauge from "@/components/ScoreGauge";
import MetricCard from "@/components/MetricCard";
import { getAreaReport, ApiError } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/format";

const CATEGORY_ORDER = ["housing", "employment", "safety", "transportation", "population"];

export default async function ReportPage({ params }: { params: Promise<{ fips: string }> }) {
  const { fips } = await params;

  let report;
  try {
    report = await getAreaReport(fips);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    return (
      <main className="mx-auto max-w-3xl px-6 py-24 text-center">
        <p className="text-red-500">Can&apos;t reach the CivicLens API. Make sure the backend is running.</p>
        <Link href="/" className="mt-4 inline-block text-slate-900 underline">
          Back home
        </Link>
      </main>
    );
  }

  const { location, growth_score, growth_score_label, categories, headline_changes } = report;

  return (
    <main className="min-h-screen bg-slate-50 pb-24">
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-5xl px-6 py-8">
          <Link href="/" className="text-sm text-slate-400 hover:text-slate-700">
            &larr; Back to search
          </Link>
          <div className="mt-4 flex flex-col items-start justify-between gap-8 sm:flex-row sm:items-center">
            <div>
              <h1 className="text-3xl font-bold text-slate-900">{location.name}</h1>
              <p className="mt-1 text-slate-500">
                {location.county ? `${location.county} County, ` : ""}
                {location.state}
              </p>
            </div>
            <ScoreGauge score={growth_score} label={growth_score_label} />
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-5xl px-6">
        {headline_changes.length > 0 && (
          <div className="mt-8 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
              Biggest changes, last 3 years
            </h2>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {headline_changes.map((change) => (
                <li key={change} className="flex items-center gap-2 text-sm text-slate-700">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" />
                  {change}
                </li>
              ))}
            </ul>
          </div>
        )}

        {CATEGORY_ORDER.filter((cat) => categories[cat]?.length).map((cat) => (
          <section key={cat} className="mt-10">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">
              {CATEGORY_LABELS[cat] || cat}
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {categories[cat].map((series) => (
                <MetricCard key={series.metric_key} series={series} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
