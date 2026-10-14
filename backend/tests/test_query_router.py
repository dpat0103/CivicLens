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
    # EXPLANATORY: asks why, or for an overview of one place
    ("why is the growth score what it is in", 1, Intent.EXPLANATORY),
    ("explain the employment numbers in", 1, Intent.EXPLANATORY),
    ("tell me about housing in", 1, Intent.EXPLANATORY),
    ("how is doing", 1, Intent.EXPLANATORY),
    ("what is going on in", 1, Intent.EXPLANATORY),
    ("why do and have the same employment", 2, Intent.EXPLANATORY),
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
