"use client";

import { useEffect, useState } from "react";
import LocationSearch from "@/components/LocationSearch";
import CompareTable from "@/components/CompareTable";
import {
  compareLocations,
  type Location,
  type CompareResponse,
  ApiError,
} from "@/lib/api";

export default function ComparePage() {
  const [selected, setSelected] = useState<Location[]>([]);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (selected.length < 2) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    compareLocations(selected.map((s) => s.fips))
      .then(setData)
      .catch((e) => {
        setError(
          e instanceof ApiError
            ? e.message
            : "The CivicLens API isn't responding. Start the backend on port 8000.",
        );
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [selected]);

  function addLocation(loc: Location) {
    setSelected((current) => {
      if (current.some((s) => s.fips === loc.fips)) return current;
      if (current.length >= 6) return current;
      return [...current, loc];
    });
  }

  function removeLocation(fips: string) {
    setSelected((current) => current.filter((s) => s.fips !== fips));
  }

  const full = selected.length >= 6;

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="serif text-3xl tracking-tight text-ink">Compare</h1>
      <p className="mt-2 max-w-[68ch] text-ink-muted">
        Put two to six municipalities side by side. Countywide indicators will
        repeat for municipalities that share a county.
      </p>

      <div className="mt-8 max-w-lg">
        <LocationSearch
          mode="select"
          onSelect={addLocation}
          exclude={selected.map((s) => s.fips)}
          placeholder={full ? "Six is the maximum" : "Add a municipality"}
        />
      </div>

      {selected.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2">
          {selected.map((loc) => (
            <li
              key={loc.fips}
              className="flex items-center gap-2 border border-rule-strong bg-surface px-3 py-1.5 text-sm"
            >
              <span className="text-ink">{loc.name}</span>
              <span className="text-xs text-ink-faint">{loc.county}</span>
              <button
                onClick={() => removeLocation(loc.fips)}
                aria-label={`Remove ${loc.name}`}
                className="text-ink-faint transition-colors hover:text-unfavourable"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected.length === 0 && (
        <p className="mt-6 text-sm text-ink-muted">
          Search above to add your first municipality.
        </p>
      )}

      {selected.length === 1 && (
        <p className="mt-6 text-sm text-ink-muted">
          Add one more to see the comparison.
        </p>
      )}

      {full && (
        <p className="mt-3 text-sm text-ink-faint">
          Remove one to swap in a different municipality.
        </p>
      )}

      {error && (
        <div className="mt-6 max-w-xl border-l-2 border-unfavourable bg-surface px-4 py-3">
          <p className="text-sm text-ink">{error}</p>
        </div>
      )}

      {loading && (
        <p className="mt-6 text-sm text-ink-muted">Loading comparison…</p>
      )}

      {data && !loading && (
        <div className="mt-8">
          <CompareTable data={data} />
          <p className="mt-3 max-w-[68ch] text-xs leading-relaxed text-ink-faint">
            The leading figure in each row is highlighted. For poverty, vacancy,
            rent burden, crime, unemployment and commute time, lower is treated
            as better. Rows where every municipality shares the same value are
            not highlighted, which is the normal case for countywide indicators.
          </p>
        </div>
      )}
    </main>
  );
}
