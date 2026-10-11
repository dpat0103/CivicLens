import { connection } from "next/server";
import Link from "next/link";
import LocationSearch from "@/components/LocationSearch";
import {
  getAreaReport,
  listLocations,
  type AreaReport,
  type Location,
  type MetricSeries,
} from "@/lib/api";
import { formatValue } from "@/lib/format";

// A short, deliberately chosen set. The point of the home page is to get
// someone into a report quickly, not to prove the dataset is large by
// printing all 564 municipalities into the document.
const FEATURED = [
  "Newark",
  "Jersey City",
  "Paterson",
  "Elizabeth",
  "Trenton",
  "Camden",
  "Hoboken",
  "Princeton",
];

// The worked example shown above the fold, so a first-time visitor sees
// what an answer looks like before deciding whether to search.
const EXAMPLE_TOWNS = ["Hoboken", "Montclair"] as const;
const EXAMPLE_METRICS = [
  "median_rent",
  "median_home_value",
  "median_household_income",
  "avg_commute_minutes",
];

const EXAMPLE_QUESTIONS = [
  "What is the median rent in Princeton?",
  "Compare Hoboken and Jersey City",
];

const INDICATOR_COUNT = 15;

function seriesByKey(report: AreaReport): Map<string, MetricSeries> {
  return new Map(
    Object.values(report.categories)
      .flat()
      .map((s) => [s.metric_key, s]),
  );
}

async function loadExample(byName: Map<string, Location>) {
  const towns = EXAMPLE_TOWNS.map((n) => byName.get(n));
  if (towns.some((t) => !t)) return null;
  try {
    const reports = await Promise.all(
      towns.map((t) => getAreaReport(t!.fips)),
    );
    const series = reports.map(seriesByKey);
    const rows = EXAMPLE_METRICS.map((key) => {
      const first = series.find((s) => s.has(key))?.get(key);
      return first
        ? { key, label: first.label, cells: series.map((s) => s.get(key)) }
        : null;
    }).filter((r): r is NonNullable<typeof r> => r !== null);
    return rows.length ? { towns: towns as Location[], rows } : null;
  } catch {
    return null;
  }
}

export default async function HomePage() {
  // Render per request so an "API isn't responding" page is never cached;
  // the data itself comes from the fetch cache in lib/api.ts.
  await connection();
  let locations: Awaited<ReturnType<typeof listLocations>> = [];
  let error: string | null = null;
  try {
    locations = await listLocations();
  } catch {
    error =
      "CivicLens is having trouble loading town data right now. Please try again in a minute.";
  }

  const byName = new Map(locations.map((l) => [l.name, l]));
  const featured = FEATURED.map((n) => byName.get(n)).filter(
    (l): l is NonNullable<typeof l> => Boolean(l),
  );
  const counties = new Set(locations.map((l) => l.county).filter(Boolean));
  const example = error ? null : await loadExample(byName);

  return (
    <main>
      <section className="border-b border-rule bg-surface">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 pb-14 pt-16 lg:grid-cols-[1fr_minmax(0,26rem)] lg:items-start">
          <div>
            <h1 className="serif text-4xl leading-[1.15] tracking-tight text-ink sm:text-5xl">
              Compare any two New Jersey towns in seconds.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-muted">
              Rent, home values, income, commute times and more for all{" "}
              {locations.length || 564} New Jersey towns, from official Census
              and Labor Department data, side by side.
            </p>

            <div className="mt-8 max-w-xl">
              <LocationSearch placeholder="Search a town, e.g. Montclair or Princeton" />
            </div>

            {featured.length > 0 && (
              <div className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-2">
                <span className="text-sm text-ink-faint">Popular towns</span>
                {featured.slice(0, 6).map((loc) => (
                  <Link
                    key={loc.fips}
                    href={`/report/${loc.fips}`}
                    className="rounded-full border border-rule px-3 py-1 text-sm text-ink-muted transition-colors hover:border-accent hover:text-accent"
                  >
                    {loc.name}
                  </Link>
                ))}
              </div>
            )}

            {error && (
              <div className="mt-8 max-w-xl border-l-2 border-unfavourable bg-surface px-4 py-3">
                <p className="text-sm text-ink">{error}</p>
              </div>
            )}
          </div>

          {example && (
            <aside className="border border-rule-strong bg-paper p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                Example comparison
              </p>
              <table className="mt-3 w-full text-sm">
                <thead>
                  <tr className="border-b border-rule">
                    <th className="py-2 text-left font-normal text-ink-faint">
                      <span className="sr-only">Indicator</span>
                    </th>
                    {example.towns.map((t) => (
                      <th
                        key={t.fips}
                        className="serif py-2 pl-4 text-right text-base font-semibold text-ink"
                      >
                        {t.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {example.rows.map((row) => (
                    <tr key={row.key} className="border-b border-rule last:border-b-0">
                      <td className="py-2.5 pr-3 text-ink-muted">{row.label}</td>
                      {row.cells.map((cell, i) => (
                        <td key={i} className="tabular py-2.5 pl-4 text-right text-ink">
                          {formatValue(cell?.latest_value, cell?.unit)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <Link
                href={`/compare?${example.towns.map((t) => `fips=${t.fips}`).join("&")}`}
                className="mt-4 inline-block text-sm font-medium text-accent underline underline-offset-4"
              >
                See the full comparison →
              </Link>
            </aside>
          )}
        </div>
      </section>

      {!error && (
        <section className="border-b border-rule bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-8">
            <dl className="grid grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4">
              {[
                {
                  value: locations.length.toLocaleString(),
                  label: "Towns",
                },
                { value: counties.size.toString(), label: "Counties" },
                { value: INDICATOR_COUNT.toString(), label: "Indicators tracked" },
                { value: "2019–2023", label: "Years covered" },
              ].map((stat) => (
                <div key={stat.label}>
                  <dt className="text-sm text-ink-faint">{stat.label}</dt>
                  <dd className="tabular mt-1 text-2xl font-medium text-ink">
                    {stat.value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </section>
      )}

      <section className="mx-auto max-w-6xl px-6 pt-14">
        <p className="max-w-3xl border-l-2 border-accent pl-4 text-ink">
          Every number comes straight from government data. The AI assistant
          explains the figures, but never makes one up.
        </p>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-10">
        <div className="grid gap-10 md:grid-cols-3">
          <article>
            <h2 className="serif text-xl text-ink">Look up your town</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              See housing costs, income, education and commuting for any New
              Jersey town, how each has changed since 2019, and where every
              figure came from.
            </p>
            <Link
              href="/places"
              className="mt-3 inline-block text-sm font-medium text-accent underline underline-offset-4"
            >
              Browse all towns
            </Link>
          </article>

          <article>
            <h2 className="serif text-xl text-ink">Compare towns side by side</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              Weighing a move? Put up to six towns in one table and see where
              they actually differ, instead of juggling browser tabs.
            </p>
            <Link
              href="/compare"
              className="mt-3 inline-block text-sm font-medium text-accent underline underline-offset-4"
            >
              Compare towns
            </Link>
          </article>

          <article>
            <h2 className="serif text-xl text-ink">Ask in plain English</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              Type a question and get an answer with its sources. Figures are
              read straight from the database, never generated by AI.
            </p>
            <div className="mt-3 flex flex-col items-start gap-2">
              {EXAMPLE_QUESTIONS.map((q) => (
                <Link
                  key={q}
                  href={`/ask?q=${encodeURIComponent(q)}`}
                  className="border border-rule px-3 py-1.5 text-xs text-ink-muted transition-colors hover:border-accent hover:text-accent"
                >
                  {q}
                </Link>
              ))}
            </div>
          </article>
        </div>
      </section>
    </main>
  );
}
