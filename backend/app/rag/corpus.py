"""
Corpus construction.

CivicLens has no prose to retrieve over. Its data is numeric time series,
and naive chunk-and-embed over numbers retrieves badly. So the corpus is
built in two deterministic passes:

1. Fact cards, templated directly from the metrics table. One card per
   (location, category). Every number in a card comes from a real row, and
   the card carries the FIPS, metric keys, periods, sources and provenance
   needed to cite it back.

2. Methodology documents, hand-written, explaining what the metrics mean
   and where the data has known limits. These are what let the assistant
   answer "why does Princeton look odd" without inventing a reason.

Because pass 1 is generated from the database, the corpus can never drift
from the numbers the rest of the API serves. Rebuild it whenever data is
refreshed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models
from ..scoring import SCORE_WEIGHTS, SATURATION_PCT

CATEGORY_TITLES = {
    "housing": "Housing",
    "employment": "Employment",
    "safety": "Safety",
    "population": "Population and income",
    "transportation": "Transportation",
}


@dataclass
class Chunk:
    """One retrievable unit, with everything needed to cite it."""
    chunk_id: str
    kind: str                      # "fact_card" | "methodology"
    text: str
    fips: str | None = None
    location_name: str | None = None
    category: str | None = None
    metric_keys: list[str] = field(default_factory=list)
    periods: list[int] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    provenance: str = "measured"   # "measured" | "simulated" | "mixed" | "n/a"


def _fmt(value: float, unit: str | None) -> str:
    if unit == "$":
        return f"${value:,.0f}"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "count":
        return f"{value:,.0f}"
    if unit == "min":
        return f"{value:.0f} min"
    if unit == "per 1,000":
        return f"{value:.1f} per 1,000"
    return f"{value:,.2f}"


def _resolve_provenance(values: list[str]) -> str:
    distinct = set(values)
    if not distinct:
        return "n/a"
    if len(distinct) == 1:
        return distinct.pop()
    return "mixed"


def build_fact_cards(db: Session) -> list[Chunk]:
    """One card per (location, category), templated from real rows."""
    locations = db.query(models.Location).order_by(models.Location.fips).all()
    chunks: list[Chunk] = []

    for loc in locations:
        rows = (
            db.query(models.Metric)
            .filter(models.Metric.location_id == loc.id)
            .order_by(models.Metric.metric_key, models.Metric.period)
            .all()
        )
        by_category: dict[str, list[models.Metric]] = defaultdict(list)
        for r in rows:
            by_category[r.category].append(r)

        for category, cat_rows in sorted(by_category.items()):
            by_key: dict[str, list[models.Metric]] = defaultdict(list)
            for r in cat_rows:
                by_key[r.metric_key].append(r)

            where = f"{loc.name}, {loc.state}"
            if loc.county:
                where += f" ({loc.county} County)"
            lines = [f"{where}. {CATEGORY_TITLES.get(category, category.title())} indicators."]

            metric_keys, periods, sources, urls, provs = [], [], [], [], []
            for key, series in sorted(by_key.items()):
                series.sort(key=lambda r: r.period)
                first, last = series[0], series[-1]
                # Every sentence names the municipality. Retrieval pulls
                # sentences out of their card, and "Employment in 2025 was
                # 41,127" is useless once separated from the heading that
                # said which town it belonged to. Chunks have to survive
                # being read in isolation.
                sentence = (
                    f"{loc.name} {last.label.lower()} in {last.period} was "
                    f"{_fmt(last.value, last.unit)}"
                )
                if first.period != last.period and first.value:
                    delta = ((last.value - first.value) / abs(first.value)) * 100
                    direction = "up" if delta >= 0 else "down"
                    sentence += (
                        f", {direction} {abs(delta):.1f}% from "
                        f"{_fmt(first.value, first.unit)} in {first.period}"
                    )
                lines.append(sentence + ".")

                metric_keys.append(key)
                periods.extend(r.period for r in series)
                for r in series:
                    if r.source:
                        sources.append(r.source)
                    if r.source_url:
                        urls.append(r.source_url)
                    provs.append(r.provenance or "measured")

            provenance = _resolve_provenance(provs)
            if provenance in ("simulated", "mixed"):
                lines.append(
                    "Note: some or all values in this card are simulated demonstration "
                    "data, not measured observations."
                )

            chunks.append(Chunk(
                chunk_id=f"fact:{loc.fips}:{category}",
                kind="fact_card",
                text=" ".join(lines),
                fips=loc.fips,
                location_name=loc.name,
                category=category,
                metric_keys=sorted(set(metric_keys)),
                periods=sorted(set(periods)),
                sources=sorted(set(sources)),
                source_urls=sorted(set(urls)),
                provenance=provenance,
            ))

    return chunks


# Human-readable names for the scored metrics. The corpus is read aloud by
# the assistant, and "bachelors_or_higher_pct" is a column name, not
# something to say to a person.
_METRIC_NAMES = {
    "population": "population",
    "median_household_income": "median household income",
    "median_home_value": "median home value",
    "bachelors_or_higher_pct": "share of adults with a bachelor's degree",
    "poverty_rate": "poverty rate",
    "employment": "countywide employment",
    "new_housing_permits": "new housing permits",
    "property_crime_rate": "property crime rate",
    "violent_crime_rate": "violent crime rate",
}


def _scoring_doc() -> str:
    weight_lines = []
    for key, cfg in SCORE_WEIGHTS.items():
        sense = "higher is better" if cfg["direction"] == 1 else "lower is better"
        name = _METRIC_NAMES.get(key, key.replace("_", " "))
        weight_lines.append(f"{name} at {int(cfg['weight'] * 100)}% ({sense})")
    return (
        "The Growth Score is a 0 to 100 composite "
        "built from the three-year percent change of six weighted indicators: "
        + ", ".join(weight_lines) + ". "
        f"Each metric's change is clamped to plus or minus {SATURATION_PCT:.0f}% before scoring, "
        "so a single outlier cannot dominate the result. The clamped value is mapped onto a "
        "0 to 100 scale and combined using the weights above, then divided by the total weight "
        "of the metrics that actually had data. Scores of 75 and above are labeled strong growth, "
        "60 to 75 moderate growth, 40 to 60 stable, 25 to 40 moderate decline, and below 25 "
        "strong decline. When a metric is missing its exact three-year data point, the nearest "
        "earlier observation is used as the baseline instead, and the period actually used is "
        "reported alongside the change. If no earlier observation exists at all, the metric is "
        "excluded from the score rather than estimated. Because the score is renormalized over "
        "whatever weight actually contributed, two municipalities can show the same score while "
        "being computed from a different number of metrics. Every score is therefore reported "
        "with its metric coverage, showing how many of the six scored metrics had usable data. "
        "Always compare coverage alongside the score before comparing two places."
    )


def build_methodology_docs() -> list[Chunk]:
    """Hand-written documents covering metric definitions and known data limits.
    These encode the real engineering tradeoffs made while building the ingestion
    layer, so the assistant can explain them instead of guessing."""
    docs: list[tuple[str, str, str]] = [
        (
            "meth:growth_score",
            "Growth Score methodology",
            _scoring_doc(),
        ),
        (
            "meth:bls_geography",
            "Why employment data is countywide",
            "Employment and unemployment figures in CivicLens come from the Bureau of Labor "
            "Statistics Local Area Unemployment Statistics program. BLS area codes below the "
            "county level are opaque and cannot be derived deterministically from a municipality "
            "name or FIPS code, so city-level lookups are unreliable. CivicLens therefore reports "
            "employment and unemployment at the county level and labels those figures Countywide. "
            "This means two municipalities in the same county share identical employment numbers. "
            "That is expected behavior, not a bug, and it is a deliberate tradeoff of precision "
            "for correctness.",
        ),
        (
            "meth:census_geography",
            "Census geography resolution",
            "Census geography classifications are not consistent across New Jersey municipalities. "
            "Some places carry no type suffix at all, as with Princeton. Others are recorded as "
            "county subdivisions rather than places, as with Montclair. A single-pass lookup against "
            "the Census place endpoint silently misses these. CivicLens resolves geography in two "
            "passes, first against places and then falling back to county subdivisions, which covers "
            "the edge cases. If a municipality appears to be missing, this resolution step is the "
            "first place to look.",
        ),
        (
            "meth:acs_estimates",
            "What ACS 5-year estimates actually are",
            "Housing, income, population and commute figures come from the American Community Survey "
            "5-year estimates. Each release pools five years of survey responses, so a value labeled "
            "2023 reflects conditions across roughly 2019 through 2023, not that single year. "
            "Consecutive ACS 5-year releases overlap by four years of sample, which means year-over-year "
            "changes are heavily smoothed and small single-year movements should not be read as real "
            "shifts. Three-year and five-year changes are more meaningful than one-year changes. "
            "ACS estimates also carry margins of error that widen considerably for smaller municipalities.",
        ),
        (
            "meth:provenance",
            "Measured versus simulated data",
            "Every metric observation in CivicLens carries a provenance flag on the individual row. "
            "A value marked measured was pulled from the live Census or BLS APIs. A value marked "
            "simulated was produced by the seed script, which generates realistic demonstration data "
            "so the application runs end to end without API keys. Provenance is tracked per row rather "
            "than per series because a metric can be measured for recent years and backfilled for older "
            "ones, which makes a single series-level label wrong. Any answer that draws on simulated "
            "values must say so explicitly.",
        ),
        (
            "meth:crime_data",
            "Crime rate caveats",
            "Property and violent crime rates are drawn from New Jersey State Police Uniform Crime "
            "Reporting summary data and are expressed per 1,000 residents. Reporting is voluntary and "
            "agency participation varies year to year, so an apparent drop in crime can reflect a "
            "reporting gap rather than an actual decline. Rates are also sensitive to the population "
            "denominator, which means a municipality with a large daytime or commuter population can "
            "look worse than residents experience. Crime figures carry a negative weight in the Growth "
            "Score, so lower values raise the score.",
        ),
    ]
    return [
        Chunk(chunk_id=cid, kind="methodology", text=f"{title}. {body}", provenance="n/a")
        for cid, title, body in docs
    ]


def build_corpus(db: Session) -> list[Chunk]:
    return build_fact_cards(db) + build_methodology_docs()