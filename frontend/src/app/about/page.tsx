import Link from "next/link";

export const metadata = {
  title: "Method | CivicLens",
  description:
    "Where CivicLens data comes from, how the Growth Score is calculated, and what the figures cannot tell you.",
};

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-rule py-10 first:border-t-0 first:pt-0">
      <h2 className="serif text-2xl tracking-tight text-ink">{title}</h2>
      <div className="mt-4 max-w-[68ch] space-y-4 leading-relaxed text-ink-muted">
        {children}
      </div>
    </section>
  );
}

export default function AboutPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="max-w-[68ch]">
        <h1 className="serif text-3xl tracking-tight text-ink">Method</h1>
        <p className="mt-3 text-lg leading-relaxed text-ink-muted">
          What the figures are, where they come from, and what they cannot tell
          you. Nothing here is proprietary. Every number can be traced back to a
          federal survey you can check yourself.
        </p>
      </div>

      <div className="mt-12">
        <Section title="Where the data comes from">
          <p>
            Housing, income, education, poverty and commuting figures come from
            the U.S. Census Bureau&rsquo;s American Community Survey 5-Year
            Estimates, vintages 2019 through 2023. Employment and unemployment
            come from the Bureau of Labor Statistics Local Area Unemployment
            Statistics programme over the same period.
          </p>
          <p>
            Both are pulled directly from the agencies&rsquo; public APIs and
            stored with the survey, vintage and source URL attached to each
            individual observation.
          </p>
        </Section>

        <Section title="What an ACS 5-year estimate actually is">
          <p>
            Each release pools five years of survey responses. A figure labelled
            2023 reflects conditions across roughly 2019 to 2023, not that
            single year. Consecutive releases overlap by four years of sample,
            so year-over-year movement is heavily smoothed and small one-year
            changes should not be read as real shifts.
          </p>
          <p>
            Three-year changes are more meaningful than one-year changes.
            Margins of error widen considerably for smaller municipalities, and
            for the smallest ones the Census suppresses some estimates entirely,
            which is why a few municipalities are missing rent or income
            figures.
          </p>
        </Section>

        <Section title="Why employment is countywide">
          <p>
            BLS area codes below the county level are opaque and cannot be
            derived reliably from a municipality name or FIPS code. Rather than
            guess at a municipal code and publish a figure that looks precise
            and is quietly wrong, CivicLens reports employment and unemployment
            at the county level and labels them{" "}
            <span className="text-ink">Countywide</span>.
          </p>
          <p>
            This means every municipality in a county shares the same employment
            numbers. That is expected, not a defect, and it is a deliberate
            trade of apparent precision for accuracy.
          </p>
        </Section>

        <Section title="How the Growth Score is calculated">
          <p>
            The Growth Score is a 0 to 100 composite of the three-year percent
            change in six weighted indicators: population and median household
            income at 20% each, median home value, share of adults holding a
            bachelor&rsquo;s degree or higher, poverty rate and countywide
            employment at 15% each. Poverty carries a negative weight, so a
            falling poverty rate raises the score.
          </p>
          <p>
            Each change is clamped to plus or minus 25% before scoring, so a
            single outlier cannot dominate. When a municipality is missing an
            exact three-year data point, the nearest earlier observation is used
            and the period actually used is reported alongside the figure. When
            no earlier observation exists, the indicator is excluded rather than
            estimated.
          </p>
          <p>
            Because the score is renormalised over whatever weight actually
            contributed, two municipalities can share a score while being
            computed from different numbers of indicators. Every score is
            therefore published with its indicator coverage, and coverage should
            be read alongside the score before comparing two places.
          </p>
        </Section>

        <Section title="Everything here is measured">
          <p>
            Every observation carries a flag recording whether it was measured
            or simulated. Every figure currently published is measured, drawn
            from the Census and BLS APIs and covering 2019 through 2023.
          </p>
          <p>
            An earlier version of this project shipped generated figures for
            crime, housing permits and transit in a handful of municipalities,
            so the application could run without API keys. Those were removed
            once real ingestion covered the state: an indicator present for
            fifteen of 564 municipalities is not comparable across New Jersey,
            which is the entire point here, and a report showing a 2023
            population beside a 2025 crime rate is misleading regardless of how
            it is labelled.
          </p>
          <p>
            The provenance flag stays. It is what identified those rows, and it
            becomes useful again the moment a crime or permits source is
            connected. Provenance is tracked per observation rather than per
            series, because a series can be measured in recent years and
            backfilled in older ones, which makes one series-level label wrong.
          </p>
        </Section>

        <Section title="Why nothing is dated after 2023">
          <p>
            ACS 5-year estimates are published on a lag, and 2023 is the most
            recent vintage available. CivicLens shows what has been measured and
            does not project forward, so no figure on this site is dated later
            than 2023.
          </p>
        </Section>

        <Section title="How the assistant answers">
          <p>
            Questions asking for a figure are answered by querying the database
            directly. No language model is involved in producing those numbers,
            so there is no opportunity to fabricate one.
          </p>
          <p>
            Questions asking why something is the case are answered from indexed
            records: fact summaries generated from the database, plus the
            methodology notes on this page. Those answers are written by a
            language model, but only from retrieved records, and every answer
            shows which records it drew on. Answers of the two kinds are
            labelled differently, because they carry different degrees of
            certainty.
          </p>
          <p>
            When nothing relevant is indexed, the assistant says so rather than
            answering anyway.
          </p>
        </Section>

        <Section title="What this cannot tell you">
          <p>
            Survey estimates describe a population in aggregate over a five-year
            window. They cannot tell you what a street is like, whether a school
            is good, or what has changed in the last eighteen months.
          </p>
          <p>
            The Growth Score is a summary of six indicators moving over three
            years. It is not a ranking of quality of life, and the weights are a
            judgement rather than a finding. Read the underlying indicators
            before drawing a conclusion from the composite.
          </p>
        </Section>
      </div>

      <div className="mt-12 border-t border-rule pt-8">
        <Link
          href="/places"
          className="text-sm font-medium text-accent underline underline-offset-4"
        >
          Browse municipalities
        </Link>
      </div>
    </main>
  );
}
