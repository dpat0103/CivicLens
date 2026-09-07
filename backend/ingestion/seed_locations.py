"""
Seed the Location table with every New Jersey municipality.

Why county subdivisions, not places
-------------------------------------
An earlier version of this script queried the Census `place` endpoint.
That was wrong for New Jersey, and the live run proved it:

    Census returned 700 NJ places.
    291 could not be matched to a county.

Every one of those 291 was a CDP -- a Census Designated Place, which is a
statistical area for an unincorporated community with no municipal
government. CDPs correctly don't appear in the county subdivision list,
because they aren't municipalities.

Worse was the number that didn't appear in that output. Of the 700 places,
about 409 were incorporated. New Jersey has 564 municipalities. So the
place endpoint was never going to return roughly 155 of them, mostly
townships, and the script would have silently seeded three quarters of the
state while reporting success.

New Jersey is a strong minor-civil-division state: every square inch of it
belongs to an incorporated municipality, and those municipalities ARE the
county subdivisions (MCDs). So `county subdivision` is not a fallback for
awkward edge cases here, it is the authoritative list.

Using it also removes an entire class of problem. The subdivision response
carries the county FIPS directly, so there is no name matching between two
geography levels, which means no Princeton-has-no-type-suffix case and no
Montclair-is-a-subdivision-not-a-place case. Those edge cases were real,
but they were artifacts of joining two endpoints that didn't need joining.

FIPS format here is state(2) + county(3) + subdivision(5) = 10 digits,
which is the standard full MCD GEOID.

Usage:
    export CENSUS_API_KEY=your_key_here
    python -m ingestion.seed_locations --year 2023

    # after the earlier place-based run, to remove the CDP rows it created:
    python -m ingestion.seed_locations --year 2023 --prune

Safe to re-run. Existing locations are matched by normalized name and
updated in place rather than duplicated.
"""
import argparse
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from app.database import Base, SessionLocal, engine
from app import models
from app.nj_counties import NJ_COUNTIES

ACS_BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"

_TRAILING_STATE = re.compile(r",\s*New Jersey\s*$", re.IGNORECASE)
_TRAILING_COUNTY_CLAUSE = re.compile(r",\s*[\w\s]+?\s+County\s*$", re.IGNORECASE)
_TRAILING_TYPE_WORD = re.compile(
    r"\s+(city|town|borough|village|township|municipality)\s*$", re.IGNORECASE
)

# Census emits placeholder rows for territory not inside a real subdivision.
# They are not municipalities and must not become Location rows.
_NOT_A_MUNICIPALITY = re.compile(r"not defined|not comparable", re.IGNORECASE)


_TYPE_WORD_CAPTURE = re.compile(
    r"\s+(city|town|borough|village|township|municipality)\s*$", re.IGNORECASE
)


def base_and_type(name: str) -> tuple[str, str | None]:
    """Split 'Washington township, Morris County, New Jersey' into
    ('washington', 'Township'). The type word is dropped by normalize() for
    matching, but is needed to build a readable disambiguated label."""
    stripped = _TRAILING_STATE.sub("", name)
    stripped = _TRAILING_COUNTY_CLAUSE.sub("", stripped).strip()
    match = _TYPE_WORD_CAPTURE.search(stripped)
    type_word = match.group(1).title() if match else None
    base = _TYPE_WORD_CAPTURE.sub("", stripped).strip().lower()
    return base, type_word


def normalize(name: str) -> str:
    """'Montclair township, Essex County, New Jersey' -> 'montclair'.

    Stripped stepwise rather than with one regex, because a pattern that
    requires a type word silently fails on names that lack one, such as
    Princeton. That failure is silent rather than an exception, which is
    how it survived the first draft of this function undetected.
    """
    stripped = _TRAILING_STATE.sub("", name)
    stripped = _TRAILING_COUNTY_CLAUSE.sub("", stripped)
    stripped = _TRAILING_TYPE_WORD.sub("", stripped)
    return stripped.strip().lower()


def fetch_municipalities(year: int, api_key: str) -> list[dict]:
    """Every NJ county subdivision, which is every NJ municipality."""
    resp = requests.get(
        ACS_BASE_URL.format(year=year),
        params={
            "get": "NAME,B01003_001E",
            "for": "county subdivision:*",
            "in": "state:34 county:*",
            "key": api_key,
        },
        timeout=60,
    )
    resp.raise_for_status()
    header, *rows = resp.json()
    idx = {name: i for i, name in enumerate(header)}

    out = []
    for row in rows:
        census_name = row[idx["NAME"]]
        if _NOT_A_MUNICIPALITY.search(census_name):
            continue

        county_fips = row[idx["county"]]
        county_name = NJ_COUNTIES.get(county_fips)
        if not county_name:
            # Unknown county code. Skip rather than guess, since a wrong
            # county silently misroutes the countywide BLS employment data.
            continue

        pop_raw = row[idx["B01003_001E"]]
        base, type_word = base_and_type(census_name)
        out.append({
            "census_name": census_name,
            "match_name": base,
            "type_word": type_word,
            "fips": f"34{county_fips}{row[idx['county subdivision']]}",
            "county": county_name,
            "population": float(pop_raw) if pop_raw not in (None, "-666666666") else None,
        })
    return out


def assign_display_names(municipalities: list[dict]) -> None:
    """Give every municipality a unique, human-readable name.

    New Jersey reuses municipality names heavily across counties: there are
    multiple Washington Townships, Franklin Townships, Union Townships and
    so on. Keying on the bare name collapses them into a single row, which
    is exactly what happened on the first live run -- 564 municipalities
    came back and only 534 survived, with 30 lost to silent overwrites.

    So a name is only used bare when it is unique statewide. When it is
    not, the type word and county are appended, producing 'Washington
    Township (Morris County)'. That keeps the common case clean while
    making the ambiguous ones distinguishable in search, in comparisons,
    and to the assistant's place resolver.
    """
    counts: dict[str, int] = {}
    for muni in municipalities:
        counts[muni["match_name"]] = counts.get(muni["match_name"], 0) + 1

    for muni in municipalities:
        base_title = muni["match_name"].title()
        if counts[muni["match_name"]] == 1:
            muni["display_name"] = base_title
        elif muni["type_word"]:
            muni["display_name"] = f"{base_title} {muni['type_word']} ({muni['county']} County)"
        else:
            muni["display_name"] = f"{base_title} ({muni['county']} County)"


def seed(year: int, api_key: str, min_population: float = 0, prune: bool = False) -> dict:
    municipalities = fetch_municipalities(year, api_key)
    assign_display_names(municipalities)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        all_locations = db.query(models.Location).all()
        # Keyed on FIPS, not name. Name is not unique for NJ municipalities
        # (multiple Washington Townships, Franklin Townships, and so on), so
        # a name-keyed dict silently collapses them and the later ones
        # overwrite the earlier ones instead of being inserted.
        by_fips = {loc.fips: loc for loc in all_locations}
        by_name = {loc.name.strip().lower(): loc for loc in all_locations}

        created, updated, skipped_small = 0, 0, 0
        authoritative_fips = set()

        for muni in municipalities:
            if muni["population"] is not None and muni["population"] < min_population:
                skipped_small += 1
                continue

            authoritative_fips.add(muni["fips"])

            # Match on FIPS first. Fall back to name only for the original
            # pilot rows, which still carry placeholder FIPS codes and can
            # only be found by name on this first real run.
            location = by_fips.get(muni["fips"])
            if location is None:
                candidate = by_name.get(muni["display_name"].lower())
                # Only adopt a name match if that row hasn't already been
                # claimed by a different municipality this run, otherwise
                # two same-named townships would fight over one row.
                if candidate is not None and candidate.fips not in authoritative_fips:
                    location = candidate

            if location is not None:
                location.fips = muni["fips"]
                location.name = muni["display_name"]
                location.county = muni["county"]
                by_fips[muni["fips"]] = location
                updated += 1
            else:
                db.add(models.Location(
                    fips=muni["fips"],
                    name=muni["display_name"],
                    state="NJ",
                    county=muni["county"],
                    location_type="city",
                ))
                created += 1

        db.flush()

        pruned = []
        if prune:
            # Remove rows that aren't real NJ municipalities, which is how
            # the CDPs from the earlier place-based run get cleaned up.
            # Only rows with no metrics attached are removed, so anything
            # carrying real ingested data is never silently deleted.
            for loc in db.query(models.Location).all():
                if loc.fips in authoritative_fips:
                    continue
                metric_count = (
                    db.query(models.Metric).filter(models.Metric.location_id == loc.id).count()
                )
                if metric_count == 0:
                    pruned.append(loc.name)
                    db.delete(loc)

        db.commit()

        ambiguous = sum(1 for m in municipalities if m["display_name"] != m["match_name"].title())
        return {
            "municipalities_returned": len(municipalities),
            "created": created,
            "updated": updated,
            "skipped_below_min_population": skipped_small,
            "pruned": pruned,
            "disambiguated_names": ambiguous,
            "total_locations": db.query(models.Location).count(),
        }
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument(
        "--min-population", type=float, default=0,
        help="Skip municipalities below this population. Default 0 (keep all 564).",
    )
    parser.add_argument(
        "--prune", action="store_true",
        help="Delete existing metric-less Location rows that aren't real NJ "
             "municipalities. Use this to clean up after the earlier place-based run.",
    )
    args = parser.parse_args()

    key = os.getenv("CENSUS_API_KEY")
    if not key:
        raise SystemExit("Set CENSUS_API_KEY in your environment first.")

    result = seed(args.year, key, args.min_population, args.prune)
    print(f"Census returned {result['municipalities_returned']} NJ municipalities.")
    print(f"Created {result['created']}, updated {result['updated']} Location rows.")
    if result["skipped_below_min_population"]:
        print(f"Skipped {result['skipped_below_min_population']} below the population floor.")
    if result["pruned"]:
        print(f"Pruned {len(result['pruned'])} non-municipality rows with no metrics attached.")
    if result["disambiguated_names"]:
        print(f"{result['disambiguated_names']} municipalities share a name with another "
              f"and were labelled with their county, e.g. 'Washington Township (Morris County)'.")
    print(f"Total locations now: {result['total_locations']}")
    print()
    print("Every municipality has a county, so none will be skipped by the BLS batch job.")