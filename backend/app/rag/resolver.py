"""
Municipality resolution.

Turning "how's Jersey City doing" into a FIPS code before retrieval runs is
what makes the metadata filter possible. Matching is longest-name-first
because New Jersey place names collide by substring: "Union City" contains
"Union", and matching greedily left to right would resolve the wrong place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import models


@dataclass
class ResolvedPlace:
    fips: str
    name: str
    county: str | None
    matched_text: str


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def resolve_places(db: Session, query: str) -> list[ResolvedPlace]:
    """Return every municipality mentioned in the query, in order of appearance."""
    locations = db.query(models.Location).all()
    haystack = f" {_normalize(query)} "

    candidates: list[tuple[int, ResolvedPlace]] = []
    consumed: list[tuple[int, int]] = []

    # Longest names first so "Union City" wins over "Union".
    for loc in sorted(locations, key=lambda l: len(l.name), reverse=True):
        needle = f" {_normalize(loc.name)} "
        start = haystack.find(needle)
        if start == -1:
            continue
        end = start + len(needle)
        # Skip if this span overlaps a longer name already matched.
        if any(start < c_end and end > c_start for c_start, c_end in consumed):
            continue
        consumed.append((start, end))
        candidates.append((start, ResolvedPlace(
            fips=loc.fips, name=loc.name, county=loc.county, matched_text=loc.name,
        )))

    return [place for _, place in sorted(candidates, key=lambda p: p[0])]


def known_place_names(db: Session) -> list[str]:
    return sorted(loc.name for loc in db.query(models.Location).all())


def strip_places(query: str, places: list[ResolvedPlace]) -> str:
    """Remove matched municipality names from the query text.

    Metric keywords are matched as substrings, and New Jersey place names
    collide with them: "Trenton" contains "rent", so "compare Princeton and
    Trenton" would detect a median_rent request that the user never made.
    Place resolution has already consumed those spans, so removing them before
    metric detection eliminates the collision entirely.
    """
    cleaned = _normalize(query)
    for place in places:
        cleaned = cleaned.replace(_normalize(place.name), " ")
    return cleaned
