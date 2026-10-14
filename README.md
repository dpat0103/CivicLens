# CivicLens

[![CI](https://github.com/dpat0103/CivicLens/actions/workflows/ci.yml/badge.svg)](https://github.com/dpat0103/CivicLens/actions/workflows/ci.yml)

**Compare any two New Jersey towns in seconds.** Rent, home values, income,
commute times and more for all 564 NJ towns, from official Census and Labor
Department data, side by side.

### [→ Try it live](https://civic-lens-khaki.vercel.app/)

**What you can do**

- **Look up a town.** See housing costs, income, education and commuting for
  any New Jersey municipality, how each has changed since 2019, and the source
  of every figure.
- **Compare towns side by side.** Put up to six towns in one table to see where
  they actually differ.
- **Ask in plain English.** "What is the median rent in Princeton?" gets an
  answer with its sources. Figures come straight from the database, and any
  number in an AI-written explanation is checked against the source records
  before it is shown.

**564 towns · 15 indicators · 2019–2023 · ~40,000 observations**

<img width="1895" height="913" alt="CivicLensOverview" src="https://github.com/user-attachments/assets/15fab2eb-0b05-4437-ac82-b2da96de5a8b" />
<img width="1887" height="912" alt="CivicLensAsk" src="https://github.com/user-attachments/assets/ce6ee297-5283-42d6-9cab-11d3831fb322" />
<img width="1886" height="913" alt="CivicLensCompare" src="https://github.com/user-attachments/assets/4052e28f-690d-4df4-8986-7d77684e9107" />

---

**For engineers:** the interesting part is below. It covers reconciling
several agencies' data formats into one comparable dataset, and a question-answering
layer where every figure comes from SQL or is verified against the records
it was quoted from.

---

## Contents

- [The problem](#the-problem)
- [The central design decision](#the-central-design-decision)
- [What it looks like in practice](#what-it-looks-like-in-practice)
- [Data](#data)
- [Architecture](#architecture)
- [Retrieval](#retrieval)
- [Testing](#testing)
- [Four bugs worth reading about](#four-bugs-worth-reading-about)
- [What I would do differently](#what-i-would-do-differently)
- [Running it](#running-it)

---

## The problem

New Jersey publishes municipal statistics across several federal and state
agencies. Each uses its own geography scheme, release cadence and naming
conventions. Answering something as simple as "is rent rising faster in
Montclair or Bloomfield" means reconciling those formats by hand first.

CivicLens does that reconciliation once and serves the result: a per-town
report, a side-by-side comparison, and an assistant that answers questions
about the data.

The interesting engineering is not the interface. It is the ingestion
reconciliation, and the constraint the assistant is built around.

---

## The central design decision

**Values come from SQL. Any number in generated prose is verified against the
records it was written from before it is shown.**

A model handed a table of figures will produce a fluent, confident, wrong
one. Prompt instructions reduce that. They do not eliminate it. So the
guarantee is enforced in code, in two layers.

**1. Value questions never reach a model.** A question asking for a figure,
or comparing places on a metric, is answered by a SQL query and a format
string.

```
question
   │
   ▼
resolve municipality names → FIPS codes
   │
   ▼
classify intent
   │
   ├── LOOKUP ──────→ SQL → format string                     no model
   ├── COMPARE ─────→ SQL → format string                     no model
   │                  (+ retrieved explanation if it asks why, checked as below)
   ├── EXPLANATORY ─→ retrieve → model → numeric check
   ├── METHODOLOGY ─→ retrieve → model → numeric check
   └── UNSUPPORTED ─→ refuse, with suggestions
```

Two or more places plus a known metric always route to COMPARE, even when
the question is phrased as advice ("Should I move to Montclair or Bloomfield
for cheaper rent?") or asks why. A test injects a model that raises if it is
ever reached on these paths:

```python
def test_lookup_never_invokes_the_model(db):
    class ExplodingLLM:
        def generate(self, system, user):
            raise AssertionError("the model was reached on a numeric lookup")

    result = answer_question(db, "What is the median rent in Montclair?", llm=ExplodingLLM())
    assert result["intent"] == "lookup"
    assert result["retrieval"]["used"] is False
```

**2. Generated prose is checked number by number.** Explanatory answers are
written from retrieved fact cards, which contain figures, so a model could
still misquote one. After generation, `app/rag/numeric_check.py` extracts
every number in the output (integers, decimals, percentages, currency,
thousands separators), normalizes formatting, and requires each one to appear
in the retrieved context. If any does not, the generated answer is discarded
and replaced by the extractive answer, which can only quote retrieved
sentences. The response reports `"numeric_check": "failed_fallback"`, the
interface says so, and the event is logged. The check is deterministic; there
is no second model call. Tests cover a fake model that invents a figure (it
falls back) and one that only repeats context figures (it passes).

**The cost.** Intent classification is a correctness boundary: a misrouted
lookup lands in the model, where only the numeric check stands between it and
the user. That is why routing is rule-based and covered by parametrised tests
rather than being a second model call: a classifier that is itself
probabilistic would put the guarantee back on the thing it was meant to
protect against.

The interface labels which path answered, because a figure read from a table
and a sentence assembled from records carry different confidence, and prose
alone does not distinguish them.

---

## What it looks like in practice

Real responses from the current code, trimmed to the relevant fields. They
were produced by running the code against real Census and BLS figures for
Westfield, Cranford and Summit, all in Union County.

**A value question. No model involved.**

```json
{
  "intent": "lookup",
  "grounded": true,
  "retrieval_used": false,
  "numeric_check": "not_applicable",
  "answer": "Median Rent in Westfield was $2,211 in 2023, a change of +29.1% over three years.",
  "citations": ["sql:3403979040:median_rent"]
}
```

**Advice phrasing, still answered from SQL.** "Should I move to Westfield or
Cranford for cheaper rent?" names two places and a metric, so it routes to
COMPARE however it is worded.

```json
{
  "intent": "compare",
  "retrieval_used": false,
  "answer": "Westfield: Growth Score 75.1 (Strong growth, computed from 6 of 6 scored metrics). Median Rent $2,211. Cranford: Growth Score 67.9 (Moderate growth, computed from 6 of 6 scored metrics). Median Rent $2,116.",
  "citations": ["sql:3403979040:compare", "sql:3403915640:compare"]
}
```

**A why question. SQL figures, then a checked explanation.** "Why do
Westfield and Cranford have the same employment?"

```json
{
  "intent": "compare",
  "retrieval_used": true,
  "numeric_check": "passed",
  "answer": "Westfield: Growth Score 75.1 (Strong growth, computed from 6 of 6 scored metrics). Employment (Countywide) 289,684. Cranford: Growth Score 67.9 (Moderate growth, computed from 6 of 6 scored metrics). Employment (Countywide) 289,684. CivicLens therefore reports employment and unemployment at the county level and labels those figures Countywide. Cranford employment (countywide) in 2023 was 289,684, up 1.5% from 285,489 in 2019. Westfield employment (countywide) in 2023 was 289,684, up 1.5% from 285,489 in 2019.",
  "citations": [
    "sql:3403979040:compare",
    "sql:3403915640:compare",
    "fact:3403915640:employment",
    "fact:3403979040:employment",
    "meth:bls_geography",
    "fact:3403915640:transportation",
    "fact:3403979040:housing"
  ]
}
```

The explanation is only possible because the corpus contains a hand-written
note on why employment is countywide. Without it, a model asked why two towns
share a figure would invent a plausible reason. This one was written by the
extractive generator; with a hosted model configured, the same numeric check
applies to its output.

**Out of scope. A refusal, not a guess.**

```json
{
  "intent": "unsupported",
  "grounded": false,
  "answer": "Summit is in the dataset, but that question is not about an indicator CivicLens tracks.",
  "suggestions": [
    "What is the median rent in Summit?",
    "Why is the growth score what it is in Summit?"
  ]
}
```

Asking about something deliberately left out says why:

```json
{
  "intent": "unsupported",
  "answer": "CivicLens does not track crime. No source offers it for every New Jersey municipality through an API, and a figure held for only some towns cannot be compared across the state, so it is left out rather than partially covered.",
  "suggestions": ["What is the poverty rate in Summit?", "Tell me about housing in Summit"]
}
```

**Every score ships with its coverage.** From Westfield's report:

```json
{
  "growth_score": 75.1,
  "growth_score_label": "Strong growth",
  "metric_coverage": {
    "metrics_used": 6,
    "metrics_total": 6,
    "weight_covered": 1.0,
    "missing_metrics": []
  }
}
```

The composite is renormalised over whatever weight actually had data, so two
municipalities can share a score while being computed from different numbers
of indicators. Coverage is what stops that being an invisible, invalid
comparison.

---

## Data

| Indicators                                                                                         | Source            | Coverage                        |
| -------------------------------------------------------------------------------------------------- | ----------------- | ------------------------------- |
| Population, median age, household income, per-capita income, poverty rate, bachelor's degree share | Census ACS 5-Year | 564 municipalities, 2019–2023   |
| Median rent, median home value, rent burden, homeownership rate, vacancy rate                      | Census ACS 5-Year | 564 municipalities, 2019–2023   |
| Mean commute time, share commuting by transit                                                      | Census ACS 5-Year | 564 municipalities, 2019–2023   |
| Employment, unemployment rate                                                                      | BLS LAUS          | 21 counties, applied countywide |

Every observation carries a provenance flag and a source URL. Ingestion only
writes measured values, and nothing is projected. Rows left over from the
original demo seed are flagged `simulated`, labelled as demonstration data in
the interface, and found and removed by `ingestion/audit_data.py` and
`ingestion/repair_data.py`.

### Limits, stated up front

**Employment is countywide.** BLS area codes below county level cannot be
derived reliably from a municipality name or FIPS code. Rather than guess and
publish a municipal figure that looks precise and is quietly wrong, CivicLens
publishes the county figure and labels it. Every municipality in a county
shares employment numbers.

**No measured value is dated after 2023.** ACS 5-year estimates publish on a
lag.

**ACS estimates are five-year pools.** A figure labelled 2023 reflects roughly
2019 through 2023. Consecutive releases overlap by four years of sample, so
year-over-year movement is heavily smoothed and three-year changes carry more
signal. Margins widen for smaller municipalities, and the Census suppresses
some estimates entirely for the smallest, which is why a few municipalities
lack rent or income figures.

**No crime, permits or transit ridership.** Sources exist but none offers
statewide municipal coverage through an API. An indicator held for a handful
of municipalities cannot be compared across the state, and a composite that
silently drops it elsewhere means something different in every place. Left out
rather than partially included.

**The Growth Score is a judgement.** Six weighted indicators over three years.
The weights are published, not derived. It is not a ranking of quality of
life.

---

## Architecture

**Backend** Python 3.12, FastAPI, SQLAlchemy, NumPy
**Frontend** Next.js 16, TypeScript, Tailwind CSS 4, Recharts
**Data** PostgreSQL (Neon) in production, SQLite locally
**Deployment** Vercel and Render

```
.github/workflows/ci.yml   lint, format check, tests, frontend lint and build
scripts/                   start and refresh_data, as .sh and Windows .ps1
backend/
├── app/
│   ├── main.py            FastAPI app, CORS, health check, /ping
│   ├── models.py          Location and Metric schema
│   ├── scoring.py         series construction, composite score, coverage
│   ├── nj_counties.py     county reference data, BLS series ID construction
│   ├── routers/           /locations, /compare, /ask
│   └── rag/
│       ├── resolver.py       municipality names → FIPS
│       ├── query_router.py   intent classification, metric vocabulary
│       ├── corpus.py         fact cards + methodology documents
│       ├── embeddings.py     pluggable embedding providers
│       ├── lexical.py        BM25 and reciprocal rank fusion
│       ├── store.py          chunk persistence, hybrid retrieval
│       ├── llm.py            generation providers, extractive fallback
│       ├── numeric_check.py  verifies numbers in generated text
│       └── answer.py         orchestration, guardrails, citations
├── ingestion/
│   ├── seed_locations.py    every NJ municipality, from Census geography
│   ├── fetch_census.py      ACS indicators
│   ├── fetch_bls_batch.py   BLS, batched by county
│   ├── build_index.py       rebuild the retrieval index
│   ├── audit_data.py        integrity checks
│   └── repair_data.py       targeted fixes
├── scripts/                 one-off diagnostics
└── tests/
    ├── test_answer.py          numeric paths never reach a model
    ├── test_numeric_check.py   invented numbers fall back, quoted ones pass
    ├── test_query_router.py    every intent, the metric vocabulary
    ├── test_resolver.py        name matching, duplicate names
    ├── test_scoring.py         series, baselines, score and coverage
    ├── test_api.py             endpoint shapes and errors
    └── test_retrieval_eval.py  labelled retrieval eval
```

**No vector database.** Chunks and embeddings live in the same PostgreSQL
instance as the metrics they describe. A separate vector service introduces a
second datastore that can drift out of date on a refresh with nothing raising
an error. Keeping them together means retrieval filters by FIPS using the same
indexes the rest of the API uses, and rebuilding is one transaction.

The cost is brute-force NumPy ranking rather than an ANN index. At a few
thousand vectors that is microseconds, and cheaper than a network hop.
`PGVECTOR_ENABLED` is the escape hatch if that stops holding.

---

## Retrieval

The corpus is built in two deterministic passes.

**Fact cards** are templated from the metrics table, one per municipality per
category. Because they are generated, they cannot drift from what the API
serves.

**Methodology documents** are hand-written and are what let the assistant
explain a data limitation rather than invent a reason for it. The Westfield
and Cranford answer above is only correct because one of these exists.

Three things make retrieval work on this data.

**Metadata filtering before ranking.** Fact cards for neighbouring
municipalities are near-identical in shape, so similarity alone returns
Bloomfield's card for a question about Montclair. Resolving to a FIPS code and
constraining on it makes that impossible rather than unlikely.

**Hybrid ranking.** Dense vectors handle paraphrase and miss exact tokens.
BM25 is the reverse. Both run, and their rankings are combined with reciprocal
rank fusion, which fuses by _rank_ rather than score specifically because BM25
is unbounded and corpus-dependent while cosine is bounded. Normalising two
scales that different would need tuning that would not survive changing the
embedding provider.

**Self-contained chunks.** Every sentence names its municipality, because
retrieval pulls sentences out of the card that gave them their subject.

---

## Testing

The backend suite runs offline, with in-memory SQLite, the hashing embedder
and the extractive generator, so CI needs no secrets. It includes a labelled
**retrieval eval**: questions each naming the chunk that must be retrieved,
plus refusal cases, measured against a recall floor in
`tests/test_retrieval_eval.py`. Fixture data mirrors real ingestion output
(the same fifteen metrics, measured, with countywide employment), including
the duplicate township names that broke the first real run.

This exists because RAG fails differently from ordinary code. Relevance
regresses silently while every unit test passes and nothing throws. Unit tests
prove the pipeline runs. The eval set proves it retrieves the right thing.

Two eval cases are marked `xfail` rather than deleted. Both need semantic
matching the offline embedder cannot do. They are the cases that should start
passing when a hosted embedding provider is configured, which is how you
verify the upgrade bought something rather than assuming it did.

The project also ships `audit_data.py`, which checks for implausible values,
stale rows, mixed provenance and coverage gaps.

CI runs `ruff check`, `ruff format --check` and `pytest` for the backend, and
`npm run lint` and `npm run build` for the frontend, on every push to main and
every pull request.

---

## Four bugs worth reading about

**Census `place` is the wrong endpoint for New Jersey.** The first ingestion
run returned 700 places, 291 of which could not be matched to a county. All
291 were Census Designated Places, which have no municipal government. Worse
was what the output did not say: of 700 places roughly 409 were incorporated,
against New Jersey's 564 municipalities. The endpoint structurally could not
see about 155 townships. NJ is a strong minor-civil-division state, so its
municipalities _are_ county subdivisions, and that endpoint returns exactly
564 rows, each already carrying its county. Switching also deleted the
name-matching step entirely.

**Municipality names are not unique.** After switching endpoints, 564
municipalities came back and 534 landed in the database. New Jersey has
several Washington Townships and several Franklin Townships, and a name-keyed
upsert collapsed them so each silently overwrote the last. Now keyed on FIPS,
with ambiguous names labelled by county for display.

**A fallback that never ran.** The three-year change calculation had a
documented fallback for a missing exact-year observation where every branch
returned `None`. Because the seed dataset had complete coverage, the path was
never exercised. It would have appeared with real ACS gaps as indicators
silently dropping out of the composite, producing scores that looked
comparable and were not. Fixing it led to publishing coverage alongside every
score.

**An N+1 that only appeared in production.** The ingestion upsert issued one
`SELECT` per observation to check existence. Against local SQLite that is
free. Against a hosted database it is roughly 36,000 round trips, twelve to
thirty-seven minutes of latency doing nothing else, and indistinguishable from
a hang. Now one query up front and batched inserts.

The common thread: three of the four were invisible locally and only surfaced
against real data at real scale.

---

## What I would do differently

**Ingest real data first.** The project began with generated data for fifteen
municipalities, on the reasoning that the architecture could be proved before
sources were wired in. That was wrong in a specific way: the synthetic dataset
was uniform, so it exercised none of the edge cases real data has. No gaps, no
suppressed estimates, no duplicate names, no geography inconsistencies. Every
significant bug above was hidden by it.

**Test against a network database earlier.** The N+1 was invisible against
SQLite and would have shipped.

**Ask about coverage before adding a source.** Time went into indicators later
dropped for lacking statewide coverage. Whether a source covers the whole unit
of analysis should be the first question, not a discovery.

---

## Running it

Requires Python 3.12+ and Node 20+. Loading real data needs free API keys
from [Census](https://api.census.gov/data/key_signup.html) and
[BLS](https://data.bls.gov/registrationEngine/); the tests do not.

**Install**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cd ../frontend && npm install
```

**Load data.** From the repository root, with `CENSUS_API_KEY` and
`BLS_API_KEY` set in the environment or in `backend/.env`:

```bash
./scripts/refresh_data.sh        # Windows PowerShell: .\scripts\refresh_data.ps1
```

That runs, in order:

```bash
python -m ingestion.seed_locations --year 2023
python -m ingestion.fetch_census --start-year 2019 --end-year 2023
python -m ingestion.fetch_bls_batch --start-year 2019 --end-year 2023
python -m ingestion.build_index
python -m ingestion.audit_data
```

Order matters: `fetch_census` matches Location rows that `seed_locations`
creates, `fetch_bls_batch` groups by the county it populates, and
`build_index` regenerates fact cards from the metrics table so it runs after
both. For a quick look without keys, `python -m ingestion.seed_data` loads
fifteen municipalities of simulated demonstration data instead (then run
`python -m ingestion.build_index`).

**Start both servers**

```bash
./scripts/start.sh               # Windows PowerShell: .\scripts\start.ps1
```

The site is at http://localhost:3000 and the API docs at
http://localhost:8000/docs.

**Run the checks CI runs**

```bash
cd backend
ruff check . && ruff format --check . && pytest -q
cd ../frontend && npm run lint && npm run build
```

### Keeping the demo warm

The API runs on Render's free plan, which sleeps after 15 idle minutes and
takes 30–60 seconds to wake. Three things hide that:

- A free [cron-job.org](https://cron-job.org) job sends `GET /ping` every 10
  minutes. `/ping` skips the database, so Neon still autosuspends. One
  always-on service uses about 744 of Render's 750 free hours a month.
- Server-rendered pages read API data through Next's fetch cache (24 hours),
  so they never wait on a sleeping backend.
- The site header pings the API on page load, so a missed cron slot is
  covered before a visitor reaches Ask or Compare.

### Configuration

| Variable              | Default                 | Purpose                       |
| --------------------- | ----------------------- | ----------------------------- |
| `DATABASE_URL`        | local SQLite            | PostgreSQL connection string  |
| `ALLOWED_ORIGINS`     | `http://localhost:3000` | CORS origins, comma-separated |
| `EMBEDDING_PROVIDER`  | `hashing`               | `hashing`, `voyage`, `openai` |
| `LLM_PROVIDER`        | `extractive`            | `extractive`, `anthropic`     |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API base for the frontend     |

Defaults need no API keys. The offline embedder and extractive summariser are
real implementations rather than stubs, which is what lets the retrieval eval
run in CI without network access.

---

## Not built

- No map view; `Location` stores coordinates that are currently unused
- No percentile ranking, so a score carries no statewide context
- Rule-based intent routing, so unusual phrasing can misroute; the failure is
  a refusal or over-broad retrieval, never a wrong figure
- No conversation memory
- No frontend tests

---

## Sources

- [US Census Bureau, American Community Survey](https://www.census.gov/programs-surveys/acs)
- [Bureau of Labor Statistics, Local Area Unemployment Statistics](https://www.bls.gov/lau/)

CivicLens is an independent project and is not affiliated with any government
agency.
