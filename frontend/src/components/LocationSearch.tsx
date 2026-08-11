"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { searchLocations, type Location } from "@/lib/api";

export default function LocationSearch({
  placeholder = "Search a city (e.g. Jersey City, Hoboken...)",
  onSelect,
  mode = "navigate",
}: {
  placeholder?: string;
  onSelect?: (loc: Location) => void;
  mode?: "navigate" | "select";
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Location[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => {
      if (query.trim().length < 1) {
        setResults([]);
        return;
      }
      setLoading(true);
      searchLocations(query)
        .then((locs) => {
          setResults(locs.slice(0, 8));
          setOpen(true);
        })
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(handle);
  }, [query]);

  function handlePick(loc: Location) {
    setQuery(loc.name);
    setOpen(false);
    if (mode === "select" && onSelect) {
      onSelect(loc);
    } else {
      router.push(`/report/${loc.fips}`);
    }
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-slate-200 bg-white px-5 py-4 text-base shadow-sm outline-none transition focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
      />
      {loading && (
        <div className="absolute right-4 top-1/2 -translate-y-1/2 text-xs text-slate-400">
          searching...
        </div>
      )}
      {open && results.length > 0 && (
        <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          {results.map((loc) => (
            <button
              key={loc.fips}
              onClick={() => handlePick(loc)}
              className="flex w-full items-center justify-between px-5 py-3 text-left transition hover:bg-slate-50"
            >
              <span className="font-medium text-slate-900">{loc.name}</span>
              <span className="text-sm text-slate-400">
                {loc.county ? `${loc.county} County, ` : ""}
                {loc.state}
              </span>
            </button>
          ))}
        </div>
      )}
      {open && !loading && query.length > 0 && results.length === 0 && (
        <div className="absolute z-20 mt-2 w-full rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm text-slate-400 shadow-lg">
          No matching municipalities in the pilot dataset yet.
        </div>
      )}
    </div>
  );
}
