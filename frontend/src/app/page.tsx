import Link from "next/link";
import LocationSearch from "@/components/LocationSearch";
import { listLocations } from "@/lib/api";

export default async function HomePage() {
  let locations: Awaited<ReturnType<typeof listLocations>> = [];
  let error: string | null = null;
  try {
    locations = await listLocations();
  } catch {
    error = "Can't reach the CivicLens API. Make sure the backend is running on port 8000.";
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-3xl px-6 pb-24 pt-20">
        <div className="text-center">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
            CivicLens Pilot &middot; New Jersey
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            What&apos;s actually happening
            <br /> in your city?
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-slate-500">
            Housing, employment, safety, transportation, and population trends,
            normalized from public datasets into one clear picture.
          </p>
        </div>

        <div className="mt-10">
          <LocationSearch />
        </div>

        {error && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {!error && (
          <div className="mt-12">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                Pilot municipalities ({locations.length})
              </h2>
              <Link href="/compare" className="text-sm font-medium text-slate-900 underline underline-offset-4">
                Compare places &rarr;
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {locations.map((loc) => (
                <Link
                  key={loc.fips}
                  href={`/report/${loc.fips}`}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-900 hover:text-slate-900"
                >
                  {loc.name}
                  <span className="block text-xs font-normal text-slate-400">
                    {loc.county} County
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
