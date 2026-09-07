"""Ingests Census ACS 5-Year Estimates at municipality level.

Queries county subdivisions rather than places, for the reasons documented
in seed_locations.py: the place endpoint cannot see roughly 155 of New
Jersey's 564 municipalities.

Fetch several vintages, not one. A single vintage yields no percent change,
so every ACS indicator drops out of the Growth Score and the composite
collapses onto countywide employment, which is identical for every
municipality in a county.

    python -m ingestion.fetch_census --start-year 2019 --end-year 2023

Requires seed_locations.py to have run first.
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

# Mean travel time is not published as a variable at this geography level
# and has to be computed. Note that B08303_001E is the TRAVEL TIME TO WORK
# table total, meaning a count of commuters, not a duration; using it
# directly yields "commutes" in the thousands.
#
#     mean minutes = aggregate travel minutes / commuters
#                  = B08013_001E / B08303_001E
COMMUTE_AGGREGATE_MINUTES = "B08013_001E"
COMMUTE_WORKER_COUNT = "B08303_001E"

# Indicators expressed as a percentage of a denominator, as
# (numerator vars, denominator var, metric spec). Numerators are summed
# because ACS splits some concepts across several variables.
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
    """Numerator sum as a percentage of denominator, or None.

    Returns None rather than 0 for a zero denominator. A municipality with
    no housing units has no vacancy rate, and 0% would assert otherwise.
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

# Census "not available" markers. Negative magic numbers, not values.
# Inserting one poisons every downstream percent change and score.
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
    """Mean one-way commute in minutes, or None.

    Returns None for Census sentinels, zero commuters, and results outside
    a plausible range. A gap is preferable to a wrong figure here: gaps are
    reported through metric coverage, while a wrong value looks
    authoritative and propagates into every percent change downstream.
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
        # Census placeholder for territory outside any municipality.
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


def upsert(db, rows: list[dict], progress: bool = False) -> dict:
    """Write observations, replacing any existing row for the same
    (location, metric, period).

    Existing rows are loaded once into a dictionary rather than queried per
    row. The obvious implementation issues a SELECT per observation, which
    is invisible against local SQLite and brutal against a hosted database:
    a full run is roughly 36,000 observations, so at a 30ms round trip that
    is eighteen minutes of latency doing nothing but existence checks.

    One query up front, then inserts batched through bulk_insert_mappings,
    turns that into a few seconds.
    """
    locations = db.query(models.Location).filter(models.Location.state == "NJ").all()
    by_fips = {loc.fips: loc for loc in locations}
    by_name = {loc.name.strip().lower(): loc for loc in locations}

    periods = {row["period"] for row in rows}
    metric_keys = {row["metric_key"] for row in rows}

    # One query for every row this run could possibly collide with.
    existing_rows = (
        db.query(models.Metric)
        .filter(
            models.Metric.period.in_(periods),
            models.Metric.metric_key.in_(metric_keys),
        )
        .all()
    )
    existing_by_key = {
        (m.location_id, m.metric_key, m.period): m for m in existing_rows
    }
    if progress:
        print(f"  {len(existing_rows):,} existing rows loaded for comparison")

    updated, to_insert, unmatched = 0, [], set()

    for row in rows:
        location = by_fips.get(row["fips"]) or by_name.get(row["match_name"])
        if not location:
            unmatched.add(row["match_name"])
            continue

        # Fallback matched by name, so bring its FIPS up to date.
        if location.fips != row["fips"]:
            location.fips = row["fips"]
            by_fips[row["fips"]] = location

        key = (location.id, row["metric_key"], row["period"])
        existing = existing_by_key.get(key)
        if existing:
            existing.value = row["value"]
            existing.source = row["source"]
            existing.source_url = row["source_url"]
            # Reset provenance on update. A row overwritten with measured
            # values must stop carrying a stale simulated flag.
            existing.provenance = "measured"
            updated += 1
        else:
            to_insert.append(dict(
                location_id=location.id, category=row["category"],
                metric_key=row["metric_key"], label=row["label"], unit=row["unit"],
                value=row["value"], period=row["period"], source=row["source"],
                source_url=row["source_url"], provenance="measured",
            ))

    if to_insert:
        db.bulk_insert_mappings(models.Metric, to_insert)
    db.commit()

    if progress:
        print(f"  {len(to_insert):,} inserted, {updated:,} updated")

    return {
        "matched": len(to_insert) + updated,
        "inserted": len(to_insert),
        "updated": updated,
        "unmatched_names": sorted(unmatched),
    }


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
        # One API call per vintage. Consecutive 5-year vintages share four
        # years of sample, so year-over-year movement is heavily smoothed
        # and three-year gaps carry far more signal.
        print(f"Fetching ACS {year} 5-Year Estimates...")
        try:
            rows = fetch_metrics(year, key)
        except Exception as exc:
            # Older vintages are occasionally unavailable at this geography
            # level. Skip rather than abort so one gap doesn't lose the rest.
            print(f"  Skipped {year}: {exc}")
            continue

        print(f"  {len(rows):,} observations parsed, writing...")
        db = SessionLocal()
        try:
            result = upsert(db, rows, progress=True)
        finally:
            db.close()
        total += result["matched"]
        unmatched.update(result["unmatched_names"])

    print(f"\nTotal: {total} metric observations, all marked provenance=measured.")
    if unmatched:
        print(f"{len(unmatched)} municipalities had no matching Location row "
              f"(run seed_locations.py first): {', '.join(sorted(unmatched)[:10])}")