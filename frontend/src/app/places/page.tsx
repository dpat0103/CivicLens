"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listLocations, type Location } from "@/lib/api";

export default function PlacesPage() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [county, setCounty] = useState("All");
  const [query, setQuery] = useState("");

  useEffect(() => {
    listLocations()
      .then(setLocations)
      .catch(() =>
        setError(
          "The CivicLens API isn't responding. Start the backend on port 8000, then reload.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  const counties = useMemo(() => {
    const set = new Set(
      locations.map((l) => l.county).filter((c): c is string => Boolean(c)),
    );
    return ["All", ...Array.from(set).sort()];
  }, [locations]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return locations.filter((l) => {
      if (county !== "All" && l.county !== county) return false;
      if (q && !l.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [locations, county, query]);

  // Grouped alphabetically, which is how someone scanning a long list of
  // place names actually navigates it.
  const grouped = useMemo(() => {
    const map = new Map<string, Location[]>();
    for (const loc of visible) {
      const letter = loc.name[0]?.toUpperCase() ?? "#";
      const bucket = map.get(letter);
      if (bucket) bucket.push(loc);
      else map.set(letter, [loc]);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [visible]);

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="serif text-3xl tracking-tight text-ink">Municipalities</h1>
      <p className="mt-2 max-w-2xl text-ink-muted">
        All {locations.length || 564} New Jersey municipalities. Filter by
        county or search by name.
      </p>

      <div className="mt-8 flex flex-wrap items-end gap-4 border-b border-rule pb-6">
        <div className="min-w-[16rem] flex-1">
          <label
            htmlFor="place-search"
            className="block text-sm text-ink-muted"
          >
            Search by name
          </label>
          <input
            id="place-search"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Montclair"
            className="mt-1.5 w-full border border-rule bg-surface px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent"
          />
        </div>

        <div>
          <label
            htmlFor="county-filter"
            className="block text-sm text-ink-muted"
          >
            County
          </label>
          <select
            id="county-filter"
            value={county}
            onChange={(e) => setCounty(e.target.value)}
            className="mt-1.5 border border-rule bg-surface px-3 py-2 text-sm text-ink outline-none transition-colors focus:border-accent"
          >
            {counties.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        <p className="tabular pb-2 text-sm text-ink-faint">
          {visible.length} shown
        </p>
      </div>

      {loading && (
        <p className="mt-10 text-ink-muted">Loading municipalities…</p>
      )}

      {error && (
        <div className="mt-10 border-l-2 border-unfavourable bg-surface px-4 py-3">
          <p className="text-sm text-ink">{error}</p>
        </div>
      )}

      {!loading && !error && visible.length === 0 && (
        <div className="mt-10 border border-rule bg-surface px-5 py-8 text-center">
          <p className="text-ink">No municipality matches that search.</p>
          <button
            onClick={() => {
              setQuery("");
              setCounty("All");
            }}
            className="mt-2 text-sm font-medium text-accent underline underline-offset-4"
          >
            Clear filters
          </button>
        </div>
      )}

      <div className="mt-10 space-y-10">
        {grouped.map(([letter, places]) => (
          <section key={letter}>
            <h2 className="border-b border-rule pb-2 text-sm font-medium text-ink-faint">
              {letter}
            </h2>
            <ul className="mt-3 grid gap-x-8 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
              {places.map((loc) => (
                <li key={loc.fips}>
                  <Link
                    href={`/report/${loc.fips}`}
                    className="group flex items-baseline justify-between gap-3 border-b border-rule/60 py-2 transition-colors hover:border-accent"
                  >
                    <span className="text-ink transition-colors group-hover:text-accent">
                      {loc.name}
                    </span>
                    <span className="shrink-0 text-xs text-ink-faint">
                      {loc.county}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </main>
  );
}
