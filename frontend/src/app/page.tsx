import Link from "next/link";
import LocationSearch from "@/components/LocationSearch";
import { listLocations } from "@/lib/api";

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

export default async function HomePage() {
  let locations: Awaited<ReturnType<typeof listLocations>> = [];
  let error: string | null = null;
  try {
    locations = await listLocations();
  } catch {
    error =
      "The CivicLens API isn't responding. Start the backend on port 8000, then reload.";
  }

  const byName = new Map(locations.map((l) => [l.name, l]));
  const featured = FEATURED.map((n) => byName.get(n)).filter(
    (l): l is NonNullable<typeof l> => Boolean(l),
  );
  const counties = new Set(locations.map((l) => l.county).filter(Boolean));

  return (
    <main>
      <section className="border-b border-rule bg-surface">
        <div className="mx-auto max-w-6xl px-6 pb-14 pt-16">
          <div className="max-w-2xl">
            <h1 className="serif text-4xl leading-[1.15] tracking-tight text-ink sm:text-5xl">
              Every New Jersey municipality, measured the same way.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-muted">
              Census and labour statistics for all {locations.length || 564}{" "}
              municipalities, normalised into comparable figures so you can read
              one place against another without reconciling four agencies&rsquo;
              formats yourself.
            </p>
          </div>

          <div className="mt-8 max-w-xl">
            <LocationSearch />
          </div>

          {featured.length > 0 && (
            <div className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-2">
              <span className="text-sm text-ink-faint">Frequently viewed</span>
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
      </section>

      {!error && (
        <section className="border-b border-rule bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-8">
            <dl className="grid grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4">
              {[
                {
                  value: locations.length.toLocaleString(),
                  label: "Municipalities",
                },
                { value: counties.size.toString(), label: "Counties" },
                { value: "13", label: "Indicators tracked" },
                { value: "2019\u20132023", label: "Years covered" },
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

      <section className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid gap-10 md:grid-cols-3">
          <article>
            <h2 className="serif text-xl text-ink">Read one place</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              Every municipality has a report covering housing, income,
              employment, education and commuting, with each figure traced back
              to the survey it came from.
            </p>
            <Link
              href="/places"
              className="mt-3 inline-block text-sm font-medium text-accent underline underline-offset-4"
            >
              Browse municipalities
            </Link>
          </article>

          <article>
            <h2 className="serif text-xl text-ink">Set two side by side</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              Put up to six municipalities in one table to see where they
              actually differ, rather than switching between tabs and holding
              numbers in your head.
            </p>
            <Link
              href="/compare"
              className="mt-3 inline-block text-sm font-medium text-accent underline underline-offset-4"
            >
              Compare places
            </Link>
          </article>

          <article>
            <h2 className="serif text-xl text-ink">Ask about the data</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              Questions asking for a figure are answered from the database
              directly. Questions asking why are answered from the indexed
              records, with sources attached.
            </p>
            <Link
              href="/ask"
              className="mt-3 inline-block text-sm font-medium text-accent underline underline-offset-4"
            >
              Ask a question
            </Link>
          </article>
        </div>
      </section>
    </main>
  );
}
