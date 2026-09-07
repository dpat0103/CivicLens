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
    LOOKUP = "lookup"                # a specific value: answered from SQL
    COMPARE = "compare"              # two or more places: answered from SQL
    EXPLANATORY = "explanatory"      # why/how: retrieval plus generation
    METHODOLOGY = "methodology"      # about the data itself: retrieval plus generation
    UNSUPPORTED = "unsupported"      # outside what the data can answer


# Metric vocabulary. Order matters: more specific phrases are checked first
# so "unemployment rate" is not swallowed by "employment".
METRIC_PATTERNS: list[tuple[str, list[str]]] = [
    ("unemployment_rate", ["unemployment", "jobless", "out of work"]),
    ("median_household_income", ["household income", "median income", "income", "earnings", "salary"]),
    ("median_rent", ["rent", "rental", "rents", "cost of housing", "housing cost"]),
    ("new_housing_permits", ["permit", "permits", "new construction", "building permit", "new housing"]),
    ("employment", ["employment", "jobs", "employed", "workforce"]),
    ("population", ["population", "residents", "how many people", "people live"]),
    ("property_crime_rate", ["property crime", "burglary", "theft"]),
    ("violent_crime_rate", ["violent crime", "assault", "homicide"]),
    ("avg_commute_minutes", ["commute", "commuting", "travel time", "drive to work"]),
    ("transit_ridership_index", ["transit", "ridership", "public transportation", "bus", "train"]),
]

# Broad category asks. "Tell me about housing in Montclair" names no single
# metric, so metric detection finds nothing and the question used to fall
# through to a refusal despite being perfectly answerable from the fact
# cards.
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "housing": ["housing", "houses", "homes", "property market", "real estate"],
    "population": ["demographics", "people", "residents", "who lives"],
    "employment": ["jobs", "labour market", "labor market", "workforce"],
    "transportation": ["transportation", "getting around", "transit", "commuting"],
    "safety": ["safety", "crime"],
}

OVERVIEW_MARKERS = [
    "tell me about", "what about", "overview of", "how is", "how are",
    "how's", "what is going on", "what's going on", "summary of", "describe",
    "look like", "doing",
]

EXPLANATORY_MARKERS = [
    "why", "how come", "explain", "reason", "what drives", "what's driving",
    "what is driving", "because", "account for", "interpret", "what does it mean",
    "should i", "better place", "makes sense",
]

METHODOLOGY_MARKERS = [
    "how is", "how are", "how do you", "how does civiclens", "what does",
    "methodology", "calculated", "computed", "measure", "defined", "definition",
    "where does the data", "data come from", "source", "reliable", "accurate",
    "margin of error", "simulated", "real data", "growth score work",
]

COMPARE_MARKERS = ["compare", "versus", " vs ", " vs. ", "better than", "difference between", "or "]

LOOKUP_MARKERS = [
    "what is", "what's", "what was", "how much", "how many", "tell me the",
    "give me the", "current", "latest",
]


@dataclass
class RoutedQuery:
    intent: Intent
    metric_keys: list[str]
    place_count: int
    reason: str
    categories: list[str] = field(default_factory=list)


def detect_metrics(query: str) -> list[str]:
    text = f" {query.lower()} "
    found: list[str] = []
    for key, phrases in METRIC_PATTERNS:
        if any(p in text for p in phrases) and key not in found:
            found.append(key)
    # "unemployment" also contains "employment"; drop the weaker match.
    if "unemployment_rate" in found and "employment" in found:
        if "unemployment" in text and not re.search(r"\b(jobs|workforce|employed)\b", text):
            found.remove("employment")
    return found


def detect_categories(query: str) -> list[str]:
    text = f" {query.lower()} "
    return [cat for cat, phrases in CATEGORY_PATTERNS.items()
            if any(p in text for p in phrases)]


def route(query: str, place_count: int) -> RoutedQuery:
    text = f" {query.lower().strip()} "
    metrics = detect_metrics(text)
    categories = detect_categories(text)

    if place_count == 0 and any(m in text for m in METHODOLOGY_MARKERS):
        return RoutedQuery(Intent.METHODOLOGY, metrics, place_count,
                           "asks about the data or the scoring method itself")

    if any(text.strip().startswith(m) or f" {m} " in text for m in EXPLANATORY_MARKERS):
        return RoutedQuery(Intent.EXPLANATORY, metrics, place_count,
                           "asks for an explanation rather than a value")

    if place_count >= 2:
        return RoutedQuery(Intent.COMPARE, metrics, place_count,
                           "names two or more municipalities")

    if place_count == 1 and metrics:
        return RoutedQuery(Intent.LOOKUP, metrics, place_count,
                           "names one municipality and one or more metrics")

    # A municipality plus a broad topic, or a municipality plus an overview
    # phrase, is a request for a summary. Retrieval handles that; a single
    # SQL lookup does not, because there is no one metric to look up.
    if place_count == 1 and (categories or any(m in text for m in OVERVIEW_MARKERS)):
        return RoutedQuery(Intent.EXPLANATORY, metrics, place_count,
                           "asks for an overview of a municipality", categories)

    if place_count == 1 and any(m in text for m in LOOKUP_MARKERS):
        return RoutedQuery(Intent.EXPLANATORY, metrics, place_count,
                           "names a municipality without a specific metric")

    if place_count >= 1:
        # A municipality was recognised but the question is not about anything
        # CivicLens measures, e.g. "who is the mayor of Newark".
        return RoutedQuery(Intent.UNSUPPORTED, metrics, place_count,
                           "that municipality is in the dataset, but the question "
                           "is not about a metric CivicLens tracks")
    return RoutedQuery(Intent.UNSUPPORTED, metrics, place_count,
                       "no municipality or metric could be identified")