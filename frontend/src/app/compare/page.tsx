"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import LocationSearch from "@/components/LocationSearch";
import CompareTable from "@/components/CompareTable";
import { compareLocations, type Location, type CompareResponse, ApiError } from "@/lib/api";

export default function ComparePage() {
  const [selected, setSelected] = useState<Location[]>([]);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handle = setTimeout(() => {
      if (selected.length < 2) {
        setData(null);
        return;
      }
      setLoading(true);
      setError(null);
      compareLocations(selected.map((s) => s.fips))
        .then(setData)
        .catch((e) => {
          setError(e instanceof ApiError ? e.message : "Couldn't reach the CivicLens API.");
          setData(null);
        })
        .finally(() => setLoading(false));
    }, 0);
    return () => clearTimeout(handle);
  }, [selected]);

  function addLocation(loc: Location) {
    if (selected.some((s) => s.fips === loc.fips)) return;
    if (selected.length >= 6) return;
    setSelected([...selected, loc]);
  }

  function removeLocation(fips: string) {
    setSelected(selected.filter((s) => s.fips !== fips));
  }

  return (
    <main className="min-h-screen bg-slate-50 pb-24">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-700">
          &larr; Back to search
        </Link>
        <h1 className="mt-4 text-3xl font-bold text-slate-900">Compare places</h1>
        <p className="mt-1 text-slate-500">Pick 2-6 municipalities to compare side by side.</p>

        <div className="mt-6 max-w-lg">
          <LocationSearch
            mode="select"
            onSelect={addLocation}
            placeholder="Add a location to compare..."
          />
        </div>

        {selected.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {selected.map((loc) => (
              <span
                key={loc.fips}
                className="flex items-center gap-2 rounded-full bg-slate-900 px-4 py-1.5 text-sm font-medium text-white"
              >
                {loc.name}
                <button
                  onClick={() => removeLocation(loc.fips)}
                  className="text-slate-300 hover:text-white"
                  aria-label={`Remove ${loc.name}`}
                >
                  &times;
                </button>
              </span>
            ))}
          </div>
        )}

        {selected.length === 1 && (
          <p className="mt-6 text-sm text-slate-400">Add at least one more location to compare.</p>
        )}

        {error && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {loading && <p className="mt-6 text-sm text-slate-400">Loading comparison...</p>}

        {data && !loading && (
          <div className="mt-8">
            <CompareTable data={data} />
            <p className="mt-3 text-xs text-slate-400">
              Bold green values indicate the strongest figure for that metric across the
              selected locations (lower is better for crime, unemployment, and commute time).
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
