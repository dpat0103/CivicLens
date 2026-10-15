"""
Query routing.

The central design decision of this feature. Questions that ask for a
number are answered by a deterministic SQL query with no language model
anywhere in the numeric path. Only questions that ask for an explanation
go through retrieval and generation.

This is what separates CivicLens from a chatbot pointed at a database.
A model asked "what is Montclair's median rent" can produce a plausible
wrong number. A SQL query cannot. So the model is never given the
opportunity, and the class of failure that makes LLM data tools untrustworthy
is removed structurally rather than mitigated with prompt instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    LOOKUP = "lookup"  # a specific value: answered from SQL
    COMPARE = "compare"  # two or more places: answered from SQL
    EXPLANATORY = "explanatory"  # why/how: retrieval plus generation
    METHODOLOGY = "methodology"  # about the data itself: retrieval plus generation
    UNSUPPORTED = "unsupported"  # outside what the data can answer


# Metric vocabulary, one entry per metric that ingestion actually writes
# (fetch_census.py and fetch_bls_batch.py). Order matters: specific phrases
# come first and are consumed when matched, so "unemployment rate" is not
# also read as employment, and "per capita income" is not also household
# income. Phrases match whole words only: as a substring, "rent" would match
# "current".
METRIC_PATTERNS: list[tuple[str, list[str]]] = [
    ("unemployment_rate", ["unemployment rate", "unemployment", "jobless", "out of work"]),
    ("per_capita_income", ["per capita income", "per capita", "income per person"]),
    ("rent_burden_pct", ["rent burden", "rent burdened", "rent as a share of income"]),
    (
        "median_household_income",
        ["household income", "median income", "income", "incomes", "earnings", "salary", "salaries"],
    ),
    (
        "median_home_value",
        [
            "median home value",
            "home value",
            "home values",
            "house value",
            "house values",
            "home price",
            "home prices",
            "house price",
            "house prices",
            "property value",
            "property values",
        ],
    ),
    (
        "homeownership_rate",
        ["homeownership", "home ownership", "homeowners", "own their home", "owner occupied"],
    ),
    ("vacancy_rate", ["vacancy rate", "vacancy", "vacancies", "vacant"]),
    (
        "median_rent",
        ["rent", "rents", "rental", "rentals", "cost of housing", "housing cost", "housing costs"],
    ),
    ("poverty_rate", ["poverty rate", "poverty", "below the poverty line"]),
    (
        "bachelors_or_higher_pct",
        ["bachelor's degree", "bachelor's", "bachelors", "college degree", "college educated", "education"],
    ),
    ("median_age", ["median age", "average age", "how old"]),
    ("employment", ["employment", "jobs", "employed", "workforce"]),
    ("population", ["population", "residents", "how many people", "people live"]),
    (
        "transit_commute_pct",
        [
            "commute by transit",
            "commuting by transit",
            "commute by public transit",
            "transit commuters",
            "public transit",
            "public transportation",
            "transit",
            "bus",
            "buses",
            "train",
            "trains",
        ],
    ),
    (
        "avg_commute_minutes",
        ["commute time", "commute", "commutes", "commuting", "travel time", "drive to work"],
    ),
]

# Topics people ask about that CivicLens deliberately does not track: no
# source covers every New Jersey municipality through an API, and a measure
# held for only some towns cannot be compared across the state. Checked
# before metrics so "transit ridership" is refused rather than answered
# with the transit commute share.
UNTRACKED_TOPICS: dict[str, list[str]] = {
    "crime": [
        "violent crime",
        "property crime",
        "crime rate",
        "crime",
        "crimes",
        "burglary",
        "burglaries",
        "theft",
        "assault",
        "homicide",
        "murder",
        "police",
        "safety",
        "safe",
    ],
    "building permits": ["building permits", "building permit", "permits", "permit", "housing starts"],
    "transit ridership": ["transit ridership", "ridership", "riders"],
}

# Broad category asks. "Tell me about housing in Montclair" names no single
# metric, so metric detection finds nothing and the question used to fall
# through to a refusal despite being perfectly answerable from the fact
# cards. Categories mirror those ingestion writes.
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "housing": ["housing", "houses", "homes", "property market", "real estate"],
    "population": ["demographics", "people", "residents", "who lives"],
    "employment": ["jobs", "labour market", "labor market", "workforce"],
    "transportation": ["transportation", "getting around", "transit", "commuting"],
}

OVERVIEW_MARKERS = [
    "tell me about",
    "what about",
    "overview of",
    "how is",
    "how are",
    "how's",
    "what is going on",
    "what's going on",
    "summary of",
    "describe",
    "look like",
    "doing",
]

EXPLANATORY_MARKERS = [
    "why",
    "how come",
    "explain",
    "reason",
    "what drives",
    "what's driving",
    "what is driving",
    "because",
    "account for",
    "interpret",
    "what does it mean",
    "should i",
    "better place",
    "makes sense",
]

METHODOLOGY_MARKERS = [
    "how is",
    "how are",
    "how do you",
    "how does civiclens",
    "what does",
    "methodology",
    "calculated",
    "computed",
    "measure",
    "defined",
    "definition",
    "where does the data",
    "data come from",
    "source",
    "reliable",
    "accurate",
    "margin of error",
    "simulated",
    "real data",
    "growth score work",
]

COMPARE_MARKERS = ["compare", "versus", " vs ", " vs. ", "better than", "difference between", "or "]

LOOKUP_MARKERS = [
    "what is",
    "what's",
    "what was",
    "how much",
    "how many",
    "tell me the",
    "give me the",
    "current",
    "latest",
]


@dataclass
class RoutedQuery:
    intent: Intent
    metric_keys: list[str]
    place_count: int
    reason: str
    categories: list[str] = field(default_factory=list)
    # Topics from UNTRACKED_TOPICS that the question asked about.
    untracked: list[str] = field(default_factory=list)
    # Set on a COMPARE that also asks why. The figures still come from SQL;
    # this only asks the answer layer to add a retrieved explanation after
    # them, which is subject to the numeric check like any generated text.
    explain: bool = False


# Phrases that ask for a reason. Narrower than EXPLANATORY_MARKERS on
# purpose: "should I move to X or Y" wants a comparison, not an essay.
REASON_MARKERS = ("explain", "reason", "because")


def asks_for_reason(query: str) -> bool:
    text = query.lower().strip()
    return text.startswith(("why", "how come")) or any(m in text for m in REASON_MARKERS)


def _phrase_pattern(phrase: str) -> re.Pattern:
    # Lookarounds rather than  so phrases containing an apostrophe
    # ("bachelor's") still anchor on whole words.
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")


def _consume(text: str, phrases: list[str]) -> tuple[bool, str]:
    """Whether any phrase occurs as whole words, and the text with every
    occurrence blanked out so weaker patterns cannot match it again."""
    matched = False
    for phrase in phrases:
        pattern = _phrase_pattern(phrase)
        if pattern.search(text):
            matched = True
            text = pattern.sub(" ", text)
    return matched, text


def detect_untracked(query: str) -> list[str]:
    text = f" {query.lower()} "
    found = []
    for topic, phrases in UNTRACKED_TOPICS.items():
        matched, text = _consume(text, phrases)
        if matched:
            found.append(topic)
    return found


def detect_metrics(query: str) -> list[str]:
    text = f" {query.lower()} "
    for phrases in UNTRACKED_TOPICS.values():
        _, text = _consume(text, phrases)
    found: list[str] = []
    for key, phrases in METRIC_PATTERNS:
        matched, text = _consume(text, phrases)
        if matched:
            found.append(key)
    return found


def detect_categories(query: str) -> list[str]:
    text = f" {query.lower()} "
    return [
        cat
        for cat, phrases in CATEGORY_PATTERNS.items()
        if any(_phrase_pattern(p).search(text) for p in phrases)
    ]


def route(query: str, place_count: int) -> RoutedQuery:
    text = f" {query.lower().strip()} "
    metrics = detect_metrics(text)
    categories = detect_categories(text)
    untracked = detect_untracked(text)

    # Asked about something CivicLens deliberately leaves out, and nothing it
    # does track. Refused with the reason, rather than answered from the
    # nearest fact card.
    if untracked and not metrics:
        return RoutedQuery(
            Intent.UNSUPPORTED,
            metrics,
            place_count,
            "asks about a topic CivicLens does not track statewide",
            untracked=untracked,
        )

    if place_count == 0 and any(m in text for m in METHODOLOGY_MARKERS):
        return RoutedQuery(
            Intent.METHODOLOGY, metrics, place_count, "asks about the data or the scoring method itself"
        )

    # Two or more places plus a known metric is a comparison of values, so
    # it is answered from SQL even when phrased as advice or a why question
    # ("should I move to Montclair or Bloomfield for cheaper rent"). Letting
    # the explanatory markers below win would hand a numeric question to the
    # model.
    if place_count >= 2 and metrics:
        return RoutedQuery(
            Intent.COMPARE,
            metrics,
            place_count,
            "names two or more municipalities and a metric",
            explain=asks_for_reason(text),
        )

    if any(text.strip().startswith(m) or f" {m} " in text for m in EXPLANATORY_MARKERS):
        return RoutedQuery(
            Intent.EXPLANATORY, metrics, place_count, "asks for an explanation rather than a value"
        )

    if place_count >= 2:
        return RoutedQuery(Intent.COMPARE, metrics, place_count, "names two or more municipalities")

    if place_count == 1 and metrics:
        return RoutedQuery(
            Intent.LOOKUP, metrics, place_count, "names one municipality and one or more metrics"
        )

    # A municipality plus a broad topic, or a municipality plus an overview
    # phrase, is a request for a summary. Retrieval handles that; a single
    # SQL lookup does not, because there is no one metric to look up.
    if place_count == 1 and (categories or any(m in text for m in OVERVIEW_MARKERS)):
        return RoutedQuery(
            Intent.EXPLANATORY, metrics, place_count, "asks for an overview of a municipality", categories
        )

    if place_count == 1 and any(m in text for m in LOOKUP_MARKERS):
        return RoutedQuery(
            Intent.EXPLANATORY, metrics, place_count, "names a municipality without a specific metric"
        )

    if place_count >= 1:
        # A municipality was recognised but the question is not about anything
        # CivicLens measures, e.g. "who is the mayor of Newark".
        return RoutedQuery(
            Intent.UNSUPPORTED,
            metrics,
            place_count,
            "that municipality is in the dataset, but the question " "is not about a metric CivicLens tracks",
        )
    return RoutedQuery(
        Intent.UNSUPPORTED, metrics, place_count, "no municipality or metric could be identified"
    )
