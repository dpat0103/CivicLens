"""
Real ingestion job: US Census Bureau ACS 5-Year Estimates.

This is a template for pulling live population, income, rent, and
commute data per place, normalizing it to our long-format Metric
schema, and upserting it into the database. It is NOT run automatically
by this repo (no network access is assumed at setup time) -- run it
yourself once you have a Census API key.

Get a free key: https://api.census.gov/data/key_signup.html

Usage:
    export CENSUS_API_KEY=your_key_here
    python -m ingestion.fetch_census --year 2023 --state 34

Docs: https://www.census.gov/data/developers/data-sets/acs-5year.html

Matching note
--------------
The seeded pilot dataset (seed_data.py) uses placeholder FIPS codes,
not real Census place codes -- they exist only so the app runs without
any API calls. Rather than hardcoding 15 real place-FIPS codes by hand
(easy to mistranscribe, and Wikipedia's infobox "FIPS code" for NJ
municipalities is actually a different ANSI code, not the Census
place code the ACS API uses), this job matches incoming Census rows to
our Location table BY NAME, and backfills the correct real FIPS code
onto the Location the first time it gets a match. Every run after that
is a normal fips-keyed upsert.
"""
import argparse
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from app.database import SessionLocal
from app import models

ACS_BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"

# ACS variable codes -> our internal metric_key
VARIABLE_MAP = {
    "B01003_001E": ("population", "Population", "count", "population"),
    "B19013_001E": ("median_household_income", "Median Household Income", "$", "population"),
    "B25064_001E": ("median_rent", "Median Rent", "$", "housing"),
    "B08303_001E": ("avg_commute_minutes", "Average Commute", "min", "transportation"),
}

# Census place NAME field looks like "Jersey City city, New Jersey" or
# "Princeton borough, New Jersey" -- strip the place-type suffix and
# state so we can match against our plain Location.name values.
_PLACE_TYPE_SUFFIXES = re.compile(
    r"\s+(city|town|borough|village|township|CDP)\s*,.*$", re.IGNORECASE
)


def normalize_place_name(census_name: str) -> str:
    return _PLACE_TYPE_SUFFIXES.sub("", census_name).strip().lower()


def fetch_place_metrics(year: int, state_fips: str, api_key: str) -> list[dict]:
    """Pull place-level (city) estimates for one state/year."""
    variables = ",".join(VARIABLE_MAP.keys())
    params = {
        "get": f"NAME,{variables}",
        "for": "place:*",
        "in": f"state:{state_fips}",
        "key": api_key,
    }
    resp = requests.get(ACS_BASE_URL.format(year=year), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    header, *records = data
    idx = {name: i for i, name in enumerate(header)}

    results = []
    for row in records:
        place_fips = f"{row[idx['state']]}{row[idx['place']]}"
        census_name = row[idx["NAME"]]
        for var_code, (metric_key, label, unit, category) in VARIABLE_MAP.items():
            raw = row[idx[var_code]]
            if raw in (None, "-666666666"):  # Census's "not available" sentinel
                continue
            results.append(dict(
                fips=place_fips,
                census_name=census_name,
                match_name=normalize_place_name(census_name),
                category=category,
                metric_key=metric_key,
                label=label,
                unit=unit,
                value=float(raw),
                period=year,
                source="US Census ACS 5-Year Estimates",
                source_url="https://www.census.gov/programs-surveys/acs",
            ))
    return results


def upsert(db, rows: list[dict]):
    # Build a lookup once: normalized name -> Location
    locations = db.query(models.Location).filter(models.Location.state == "NJ").all()
    by_name = {loc.name.strip().lower(): loc for loc in locations}

    matched, unmatched_names, fips_backfilled = 0, set(), 0

    for row in rows:
        location = by_name.get(row["match_name"])
        if not location:
            unmatched_names.add(row["census_name"])
            continue

        if location.fips != row["fips"]:
            # First real match for this location -- replace the
            # placeholder seed FIPS with the real Census place FIPS.
            location.fips = row["fips"]
            fips_backfilled += 1

        existing = (
            db.query(models.Metric)
            .filter_by(location_id=location.id, metric_key=row["metric_key"], period=row["period"])
            .first()
        )
        if existing:
            existing.value = row["value"]
        else:
            db.add(models.Metric(
                location_id=location.id, category=row["category"], metric_key=row["metric_key"],
                label=row["label"], unit=row["unit"], value=row["value"], period=row["period"],
                source=row["source"], source_url=row["source_url"],
            ))
        matched += 1

    db.commit()
    print(f"Matched {matched} metric observations to existing locations "
          f"({fips_backfilled} locations had their FIPS code corrected to the real Census code).")
    if unmatched_names:
        print(f"Note: {len(unmatched_names)} Census place names in the response didn't match "
              f"any seeded location (expected -- NJ has 500+ places, we only seeded 15).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--state", default="34", help="State FIPS code, default 34 = New Jersey")
    args = parser.parse_args()

    key = os.getenv("CENSUS_API_KEY")
    if not key:
        raise SystemExit("Set CENSUS_API_KEY in your environment first.")

    rows = fetch_place_metrics(args.year, args.state, key)
    db = SessionLocal()
    try:
        upsert(db, rows)
    finally:
        db.close()