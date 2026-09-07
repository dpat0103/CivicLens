"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { listLocations, type Location } from "@/lib/api";

type Props = {
  /** "navigate" opens the municipality's report. "select" hands it back to
   *  the parent instead, which is what the compare page needs so it can
   *  collect several municipalities rather than leaving the page on the
   *  first pick. */
  mode?: "navigate" | "select";
  onSelect?: (loc: Location) => void;
  placeholder?: string;
  /** FIPS codes already chosen, hidden from results so a municipality can't
   *  be added to a comparison twice. */
  exclude?: string[];
};

export default function LocationSearch({
  mode = "navigate",
  onSelect,
  placeholder = "Search a municipality",
  exclude = [],
}: Props) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Location[]>([]);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      listLocations(q)
        .then((rows) => {
          if (cancelled) return;
          setResults(rows.slice(0, 20));
          setHighlighted(0);
          setOpen(true);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Applied here rather than in the fetch effect. `exclude` is an array
  // prop, so it is a new identity on every render; depending on it in an
  // effect that calls setState loops forever.
  const visible = results.filter((r) => !exclude.includes(r.fips)).slice(0, 8);

  function go(loc: Location) {
    setOpen(false);
    setQuery("");
    if (mode === "select") {
      onSelect?.(loc);
      return;
    }
    router.push(`/report/${loc.fips}`);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || visible.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlighted((i) => (i + 1) % visible.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlighted((i) => (i - 1 + visible.length) % visible.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      // `visible` can shrink when a municipality is excluded after being
      // added, leaving the highlight index past the end of the list.
      const choice = visible[highlighted] ?? visible[0];
      if (choice) go(choice);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <label htmlFor="municipality-search" className="sr-only">
        Search for a municipality
      </label>
      <input
        id="municipality-search"
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls="municipality-results"
        aria-autocomplete="list"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="w-full border border-rule-strong bg-surface px-4 py-3 text-base text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent"
      />

      {loading && query.trim().length >= 2 && !open && (
        <p className="absolute right-4 top-3.5 text-sm text-ink-faint">
          Searching…
        </p>
      )}

      {open && (
        <ul
          id="municipality-results"
          role="listbox"
          className="absolute z-20 mt-1 w-full border border-rule bg-surface shadow-sm"
        >
          {visible.length === 0 && (
            <li className="px-4 py-3 text-sm text-ink-muted">
              No municipality matches “{query.trim()}”.
            </li>
          )}
          {visible.map((loc, i) => (
            <li key={loc.fips} role="option" aria-selected={i === highlighted}>
              <button
                onMouseEnter={() => setHighlighted(i)}
                onClick={() => go(loc)}
                className={`flex w-full items-baseline justify-between gap-3 px-4 py-2.5 text-left text-sm ${
                  i === highlighted
                    ? "bg-accent-soft text-ink"
                    : "text-ink-muted"
                }`}
              >
                <span>{loc.name}</span>
                <span className="shrink-0 text-xs text-ink-faint">
                  {loc.county}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
