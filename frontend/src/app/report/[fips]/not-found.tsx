import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24 text-center">
      <h1 className="serif text-3xl tracking-tight text-ink">
        We couldn&rsquo;t find that town
      </h1>
      <p className="mt-3 text-ink-muted">
        CivicLens covers all 564 New Jersey municipalities. Try searching for
        it by name.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block bg-accent px-5 py-2.5 text-sm font-medium text-white transition-colors hover:opacity-90"
      >
        Back to search
      </Link>
    </main>
  );
}
