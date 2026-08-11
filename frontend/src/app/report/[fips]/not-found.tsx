import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24 text-center">
      <h1 className="text-2xl font-bold text-slate-900">Location not found</h1>
      <p className="mt-2 text-slate-500">
        That FIPS code isn&apos;t in the pilot dataset yet. CivicLens currently covers
        15 New Jersey municipalities.
      </p>
      <Link href="/" className="mt-6 inline-block rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white">
        Back to search
      </Link>
    </main>
  );
}
