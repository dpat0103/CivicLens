import AskPanel from "@/components/AskPanel";

export const metadata = {
  title: "Ask | CivicLens",
  description:
    "Ask questions about New Jersey municipal statistics. Figures are read from the database; explanations are drawn from indexed records with sources attached.",
};

export default function AskPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="serif text-3xl tracking-tight text-ink">
        Ask about the data
      </h1>
      <p className="mt-3 max-w-[68ch] leading-relaxed text-ink-muted">
        Two kinds of question get two kinds of answer. Asking for a figure runs
        a database query, so no language model is involved and no number can be
        invented. Asking why something is the case retrieves the relevant
        records and writes from those, with the sources shown.
      </p>

      <div className="mt-8">
        <AskPanel />
      </div>

      <section className="mt-12 border-t border-rule pt-8">
        <h2 className="serif text-xl text-ink">
          What it can and cannot answer
        </h2>
        <div className="mt-4 grid gap-8 sm:grid-cols-2">
          <div>
            <h3 className="text-sm font-medium text-ink">Answerable</h3>
            <ul className="mt-2 space-y-1.5 text-sm text-ink-muted">
              <li>Median rent, income or population for a municipality</li>
              <li>Comparisons between two or more municipalities</li>
              <li>Why employment figures repeat across a county</li>
              <li>How the Growth Score is put together</li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-medium text-ink">Outside the data</h3>
            <ul className="mt-2 space-y-1.5 text-sm text-ink-muted">
              <li>School quality, or crime beyond the indicators held</li>
              <li>Anything after 2023, or forecasts</li>
              <li>Elected officials, local news, planning applications</li>
              <li>Places outside New Jersey</li>
            </ul>
          </div>
        </div>
        <p className="mt-6 text-sm text-ink-faint">
          Questions outside the data get a plain refusal rather than a guess.
        </p>
      </section>
    </main>
  );
}
