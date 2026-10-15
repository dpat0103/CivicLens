"""Routing is a correctness boundary: a value question routed to EXPLANATORY
would put a model on the numeric path. So every intent is pinned here.

`route` receives text with place names already removed and the number of
places that were resolved, which is how answer_question calls it."""

import pytest

from app.rag.query_router import Intent, detect_categories, detect_metrics, route

ROUTING_CASES = [
    # LOOKUP: one place, one or more metrics
    ("what is the median rent in", 1, Intent.LOOKUP),
    ("how many people live in", 1, Intent.LOOKUP),
    ("median household income in", 1, Intent.LOOKUP),
    ("unemployment rate for", 1, Intent.LOOKUP),
    ("what is the average commute in", 1, Intent.LOOKUP),
    ("rent and income in", 1, Intent.LOOKUP),
    # COMPARE: two or more places
    ("compare and", 2, Intent.COMPARE),
    ("median rent in versus", 2, Intent.COMPARE),
    ("population of , and", 3, Intent.COMPARE),
    # Two places and a metric are compared from SQL even when phrased as
    # advice or a why question; explanatory markers must not win.
    ("should i move to or for cheaper rent", 2, Intent.COMPARE),
    ("which is a better place for income, or", 2, Intent.COMPARE),
    ("why do and have the same employment", 2, Intent.COMPARE),
    # EXPLANATORY: asks why, or for an overview of one place
    ("why is the growth score what it is in", 1, Intent.EXPLANATORY),
    ("explain the employment numbers in", 1, Intent.EXPLANATORY),
    ("tell me about housing in", 1, Intent.EXPLANATORY),
    ("how is doing", 1, Intent.EXPLANATORY),
    ("what is going on in", 1, Intent.EXPLANATORY),
    ("why does score lower than", 2, Intent.EXPLANATORY),
    # METHODOLOGY: about the data itself, no place named
    ("how is the growth score calculated", 0, Intent.METHODOLOGY),
    ("where does the data come from", 0, Intent.METHODOLOGY),
    ("is the data simulated or real data", 0, Intent.METHODOLOGY),
    ("what is the margin of error", 0, Intent.METHODOLOGY),
    # UNSUPPORTED: a place but nothing CivicLens measures, or nothing at all
    ("who is the mayor of", 1, Intent.UNSUPPORTED),
    ("best pizza in", 1, Intent.UNSUPPORTED),
    ("what is the capital of france", 0, Intent.UNSUPPORTED),
    ("hello", 0, Intent.UNSUPPORTED),
]


@pytest.mark.parametrize("query, places, intent", ROUTING_CASES)
def test_route(query, places, intent):
    assert route(query, places).intent is intent


def test_every_intent_is_covered():
    assert {intent for _, _, intent in ROUTING_CASES} == set(Intent)


def test_lookup_carries_the_detected_metrics():
    routed = route("rent and income in", 1)
    assert routed.metric_keys == ["median_household_income", "median_rent"]


def test_overview_carries_its_category():
    assert route("tell me about housing in", 1).categories == ["housing"]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("unemployment rate", ["unemployment_rate"]),
        ("jobs and unemployment", ["unemployment_rate", "employment"]),
        ("median household income", ["median_household_income"]),
        ("average commute time", ["avg_commute_minutes"]),
        ("how many people live here", ["population"]),
        ("nothing measurable", []),
    ],
)
def test_detect_metrics(query, expected):
    assert detect_metrics(query) == expected


def test_unemployment_does_not_also_detect_employment():
    assert "employment" not in detect_metrics("what is the unemployment rate")


def test_detect_categories():
    assert detect_categories("tell me about housing and jobs") == ["housing", "employment"]


@pytest.mark.parametrize(
    "query, explain",
    [
        ("why do and have the same employment", True),
        ("explain the rent gap between and", True),
        ("should i move to or for cheaper rent", False),
        ("compare rent in and", False),
    ],
)
def test_compare_flags_only_why_questions_for_an_explanation(query, explain):
    routed = route(query, 2)
    assert routed.intent is Intent.COMPARE
    assert routed.explain is explain


# Every metric ingestion writes is reachable by name, and nothing else is.
@pytest.mark.parametrize(
    "query, expected",
    [
        ("what is the median rent", ["median_rent"]),
        ("median home value", ["median_home_value"]),
        ("house prices", ["median_home_value"]),
        ("per capita income", ["per_capita_income"]),
        ("rent burden", ["rent_burden_pct"]),
        ("homeownership rate", ["homeownership_rate"]),
        ("vacancy rate", ["vacancy_rate"]),
        ("poverty rate", ["poverty_rate"]),
        ("share with a bachelor's degree", ["bachelors_or_higher_pct"]),
        ("median age", ["median_age"]),
        ("share who commute by transit", ["transit_commute_pct"]),
        ("public transportation", ["transit_commute_pct"]),
        ("how long is the commute", ["avg_commute_minutes"]),
    ],
)
def test_every_ingested_metric_is_detectable(query, expected):
    assert detect_metrics(query) == expected


def test_vocabulary_matches_ingested_metrics():
    from app.rag.query_router import METRIC_PATTERNS

    ingested = {
        "population",
        "median_age",
        "median_household_income",
        "per_capita_income",
        "poverty_rate",
        "bachelors_or_higher_pct",
        "median_rent",
        "median_home_value",
        "rent_burden_pct",
        "homeownership_rate",
        "vacancy_rate",
        "avg_commute_minutes",
        "transit_commute_pct",
        "employment",
        "unemployment_rate",
    }
    assert {key for key, _ in METRIC_PATTERNS} == ingested


@pytest.mark.parametrize("query", ["the current population", "what is the latest population"])
def test_metric_words_match_whole_words_only(query):
    # "current" contains "rent".
    assert detect_metrics(query) == ["population"]


def test_per_capita_income_is_not_also_household_income():
    assert detect_metrics("per capita income") == ["per_capita_income"]


@pytest.mark.parametrize(
    "query, topics",
    [
        ("what is the crime rate in", ["crime"]),
        ("is safe", ["crime"]),
        ("how many burglaries in", ["crime"]),
        ("how many building permits were issued in", ["building permits"]),
        ("transit ridership in", ["transit ridership"]),
        ("crime and permits in", ["crime", "building permits"]),
    ],
)
def test_untracked_topics_are_unsupported(query, topics):
    routed = route(query, 1)
    assert routed.intent is Intent.UNSUPPORTED
    assert routed.untracked == topics


def test_ridership_is_not_answered_with_the_commute_share():
    assert detect_metrics("transit ridership") == []


def test_tracked_metric_alongside_untracked_topic_is_still_answered():
    routed = route("crime and median rent in", 1)
    assert routed.intent is Intent.LOOKUP
    assert routed.metric_keys == ["median_rent"]


def test_no_safety_category():
    from app.rag.query_router import CATEGORY_PATTERNS

    assert set(CATEGORY_PATTERNS) == {"housing", "population", "employment", "transportation"}
