"""
Real ingestion job: US Census Bureau ACS 5-Year Estimates, at the county
subdivision (municipality) level.

Why this replaced the place-based version
-------------------------------------------
The original queried `for=place:*`. For New Jersey that returns 700 rows,
of which ~291 are CDPs (statistical areas with no municipal government)
and only ~409 are incorporated. NJ has 564 municipalities, so the place
endpoint structurally cannot see about 155 of them.

NJ municipalities are county subdivisions (MCDs), so that is the endpoint
that returns exactly the right 564 rows, each already carrying its county.

This also removes the name-matching step entirely. The old version matched
incoming Census rows to Location rows by normalized name and backfilled
FIPS on first match, which was necessary when the pilot used placeholder
FIPS codes. Now seed_locations writes real MCD GEOIDs, so this job keys on
FIPS directly. Name matching is kept only as a fallback for the original
pilot rows that may not have been re-seeded yet.

Usage:
    export CENSUS_API_KEY=your_key_here
    python -m ingestion.fetch_census --year 2023

Run seed_locations.py first.
"""
import argparse
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from app.database import SessionLocal
from app import models
from app.nj_counties import NJ_COUNTIES

ACS_BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"

# ACS variable code -> (metric_key, label, unit, category)
# Direct variables only. Anything requiring arithmetic is handled separately
# in DERIVED_METRICS below.
VARIABLE_MAP = {
    "B01003_001E": ("population", "Population", "count", "population"),
    "B01002_001E": ("median_age", "Median Age", "years", "population"),
    "B19013_001E": ("median_household_income", "Median Household Income", "$", "population"),
    "B19301_001E": ("per_capita_income", "Per Capita Income", "$", "population"),
    "B25064_001E": ("median_rent", "Median Rent", "$", "housing"),
    "B25077_001E": ("median_home_value", "Median Home Value", "$", "housing"),
    "B25071_001E": ("rent_burden_pct", "Rent as % of Income", "%", "housing"),
}

# Mean travel time to work is NOT a published variable at the county
# subdivision level. It has to be computed.
#
# The original mapping used B08303_001E directly as "Average Commute", but
# B08303 is the TRAVEL TIME TO WORK table and its _001E is the table total,
# meaning the COUNT of workers who commute. That is why townships were
# showing commutes in the thousands: those were people, not minutes.
#
# Correct form:
#     mean minutes = aggregate travel time / number of commuters
#                  = B08013_001E / B08303_001E
COMMUTE_AGGREGATE_MINUTES = "B08013_001E"
COMMUTE_WORKER_COUNT = "B08303_001E"

# Ratio metrics. Each is (numerator vars, denominator var, metric spec).
# Numerators are summed, which is what educational attainment needs since
# ACS splits it across four separate degree-level variables.
RATIO_METRICS = [
    (
        ["B25003_002E"], "B25003_001E",
        ("homeownership_rate", "Homeownership Rate", "%", "housing"),
    ),
    (
        ["B25002_003E"], "B25002_001E",
        ("vacancy_rate", "Housing Vacancy Rate", "%", "housing"),
    ),
    (
        ["B17001_002E"], "B17001_001E",
        ("poverty_rate", "Poverty Rate", "%", "population"),
    ),
    (
        # Bachelor's, master's, professional, doctorate. ACS has no single
        # "bachelor's or higher" variable, so the four are summed.
        ["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"], "B15003_001E",
        ("bachelors_or_higher_pct", "Bachelor's Degree or Higher", "%", "population"),
    ),
    (
        # Real transit data, replacing the simulated ridership index. This is
        # the share of commuters using public transportation, which is both
        # measurable per municipality and more meaningful than an index.
        ["B08301_010E"], "B08301_001E",
        ("transit_commute_pct", "Commute by Public Transit", "%", "transportation"),
    ),
]


def _ratio(numerator_raws, denominator_raw) -> float | None:
    """Percent of denominator, or None when the inputs can't support one.

    Returns None rather than 0 when the denominator is zero. A municipality
    with no housing units has no meaningful vacancy rate, and recording 0%
    would assert something false about it.
    """
    if denominator_raw in _SENTINELS:
        return None
    try:
        denominator = float(denominator_raw)
    except (TypeError, ValueError):
        return None
    if denominator <= 0:
        return None

    total = 0.0
    for raw in numerator_raws:
        if raw in _SENTINELS:
            return None
        try:
            total += float(raw)
        except (TypeError, ValueError):
            return None
    if total < 0:
        return None

    pct = (total / denominator) * 100
    if not (0 <= pct <= 100):
        return None
    return round(pct, 1)

# Census "not available" sentinels. These are negative magic numbers, not
# real values, and inserting them would poison every downstream percent
# change and growth score.
_SENTINELS = {"-666666666", "-999999999", "-888888888", "-222222222", None, ""}

_NOT_A_MUNICIPALITY = re.compile(r"not defined|not comparable", re.IGNORECASE)

_TRAILING_STATE = re.compile(r",\s*New Jersey\s*$", re.IGNORECASE)
_TRAILING_COUNTY_CLAUSE = re.compile(r",\s*[\w\s]+?\s+County\s*$", re.IGNORECASE)
_TRAILING_TYPE_WORD = re.compile(
    r"\s+(city|town|borough|village|township|municipality)\s*$", re.IGNORECASE
)


def normalize(name: str) -> str:
    stripped = _TRAILING_STATE.sub("", name)
    stripped = _TRAILING_COUNTY_CLAUSE.sub("", stripped)
    stripped = _TRAILING_TYPE_WORD.sub("", stripped)
    return stripped.strip().lower()


def _mean_commute(aggregate_raw, workers_raw) -> float | None:
    """B08013_001E / B08303_001E, with the guards that matter.

    Returns None rather than a wrong number when either input is a Census
    sentinel, when there are no commuters to divide by, or when the result
    lands outside anything a real commute could be. A silently wrong 4000
    is far more damaging than a visible gap, because the gap is now
    reported honestly by the metric coverage field.
    """
    if aggregate_raw in _SENTINELS or workers_raw in _SENTINELS:
        return None
    try:
        aggregate = float(aggregate_raw)
        workers = float(workers_raw)
    except (TypeError, ValueError):
        return None
    if aggregate < 0 or workers <= 0:
        return None
    mean = aggregate / workers
    if not (1 <= mean <= 180):
        return None
    return round(mean, 1)


def fetch_metrics(year: int, api_key: str) -> list[dict]:
    ratio_vars = []
    for numerators, denominator, _ in RATIO_METRICS:
        ratio_vars.extend(numerators)
        ratio_vars.append(denominator)
    # Census caps a single request at 50 variables. Currently ~20.
    all_vars = list(VARIABLE_MAP) + [COMMUTE_AGGREGATE_MINUTES, COMMUTE_WORKER_COUNT] + ratio_vars
    variables = ",".join(dict.fromkeys(all_vars))
    resp = requests.get(
        ACS_BASE_URL.format(year=year),
        params={
            "get": f"NAME,{variables}",
            "for": "county subdivision:*",
            "in": "state:34 county:*",
            "key": api_key,
        },
        timeout=60,
    )
    resp.raise_for_status()
    header, *rows = resp.json()
    idx = {name: i for i, name in enumerate(header)}

    results = []
    for row in rows:
        county_fips = row[idx["county"]]
        if county_fips not in NJ_COUNTIES:
            continue

        census_name = row[idx["NAME"]]
        # Census placeholder for territory outside any municipality. Not a
        # real place, and it was the single "unmatched" row reported on the
        # first live run.
        if _NOT_A_MUNICIPALITY.search(census_name):
            continue

        fips = f"34{county_fips}{row[idx['county subdivision']]}"

        for var_code, (metric_key, label, unit, category) in VARIABLE_MAP.items():
            raw = row[idx[var_code]]
            if raw in _SENTINELS:
                continue
            value = float(raw)
            if value < 0:
                # Any remaining negative is another sentinel variant. None of
                # these four metrics can legitimately be negative.
                continue
            results.append(dict(
                fips=fips,
                match_name=normalize(census_name),
                category=category,
                metric_key=metric_key,
                label=label,
                unit=unit,
                value=value,
                period=year,
                source="US Census ACS 5-Year Estimates",
                source_url="https://www.census.gov/programs-surveys/acs",
            ))

        for numerators, denominator, (metric_key, label, unit, category) in RATIO_METRICS:
            pct = _ratio([row[idx[n]] for n in numerators], row[idx[denominator]])
            if pct is None:
                continue
            results.append(dict(
                fips=fips,
                match_name=normalize(census_name),
                category=category,
                metric_key=metric_key,
                label=label,
                unit=unit,
                value=pct,
                period=year,
                source="US Census ACS 5-Year Estimates",
                source_url="https://www.census.gov/programs-surveys/acs",
            ))

        mean_commute = _mean_commute(
            row[idx[COMMUTE_AGGREGATE_MINUTES]], row[idx[COMMUTE_WORKER_COUNT]]
        )
        if mean_commute is not None:
            results.append(dict(
                fips=fips,
                match_name=normalize(census_name),
                category="transportation",
                metric_key="avg_commute_minutes",
                label="Average Commute",
                unit="min",
                value=mean_commute,
                period=year,
                source="US Census ACS 5-Year Estimates",
                source_url="https://www.census.gov/programs-surveys/acs",
            ))
    return results


def upsert(db, rows: list[dict]) -> dict:
    locations = db.query(models.Location).filter(models.Location.state == "NJ").all()
    by_fips = {loc.fips: loc for loc in locations}
    by_name = {loc.name.strip().lower(): loc for loc in locations}

    matched, unmatched = 0, set()

    for row in rows:
        location = by_fips.get(row["fips"]) or by_name.get(row["match_name"])
        if not location:
            unmatched.add(row["match_name"])
            continue

        # Fallback matched by name, so bring its FIPS up to date.
        if location.fips != row["fips"]:
            location.fips = row["fips"]
            by_fips[row["fips"]] = location

        existing = (
            db.query(models.Metric)
            .filter_by(location_id=location.id, metric_key=row["metric_key"], period=row["period"])
            .first()
        )
        if existing:
            existing.value = row["value"]
            existing.source = row["source"]
            existing.source_url = row["source_url"]
            # Critical: without this, a row seeded as demo data keeps its
            # "simulated" flag after being overwritten with real Census
            # values, and the UI keeps warning about data that is now real.
            existing.provenance = "measured"
        else:
            db.add(models.Metric(
                location_id=location.id, category=row["category"], metric_key=row["metric_key"],
                label=row["label"], unit=row["unit"], value=row["value"], period=row["period"],
                source=row["source"], source_url=row["source_url"], provenance="measured",
            ))
        matched += 1

    db.commit()
    return {"matched": matched, "unmatched_names": sorted(unmatched)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch ACS 5-Year Estimates. Fetch SEVERAL years, not one: "
                    "a single year gives no percent change, so every ACS metric "
                    "drops out of the Growth Score and only countywide employment "
                    "is left, which makes every town in a county score identically."
    )
    parser.add_argument("--year", type=int, help="Single vintage, e.g. 2023.")
    parser.add_argument("--start-year", type=int, help="First vintage, inclusive.")
    parser.add_argument("--end-year", type=int, help="Last vintage, inclusive.")
    parser.add_argument("--state", default="34", help="Kept for CLI compatibility; NJ only.")
    args = parser.parse_args()

    if args.year and (args.start_year or args.end_year):
        parser.error("Use --year on its own, or --start-year with --end-year.")
    if args.year:
        years = [args.year]
    elif args.start_year and args.end_year:
        years = list(range(args.start_year, args.end_year + 1))
    else:
        parser.error("Give --year, or --start-year and --end-year.")

    key = os.getenv("CENSUS_API_KEY")
    if not key:
        raise SystemExit("Set CENSUS_API_KEY in your environment first.")

    if len(years) == 1:
        print("NOTE: fetching a single vintage. Percent changes need at least two, "
              "and three-year changes need a gap of three.\n")

    total, unmatched = 0, set()
    for year in years:
        # Each ACS 5-year vintage is a separate API call. They overlap by four
        # years of sample, so consecutive vintages are heavily smoothed and
        # three-year gaps are far more meaningful than one-year ones.
        print(f"Fetching ACS {year} 5-Year Estimates...")
        try:
            rows = fetch_metrics(year, key)
        except Exception as exc:
            # Older vintages are sometimes unavailable at this geography level.
            # Skip rather than abort, so one missing year doesn't lose the rest.
            print(f"  Skipped {year}: {exc}")
            continue

        db = SessionLocal()
        try:
            result = upsert(db, rows)
        finally:
            db.close()
        total += result["matched"]
        unmatched.update(result["unmatched_names"])
        print(f"  Upserted {result['matched']} observations for {year}.")

    print(f"\nTotal: {total} metric observations, all marked provenance=measured.")
    if unmatched:
        print(f"{len(unmatched)} municipalities had no matching Location row "
              f"(run seed_locations.py first): {', '.join(sorted(unmatched)[:10])}")