"""
Real ingestion job: BLS LAUS, batched by county.

Why this exists instead of just calling fetch_bls.py 564 times
-----------------------------------------------------------------
fetch_bls.py takes one series ID and one location FIPS per invocation.
Calling it once per municipality would mean up to 564 requests just for
unemployment rate, doubled for employment, and BLS's registered rate limit
is 500 requests per day. It would also contradict the countywide design
already documented in the RAG methodology corpus: employment data is
reported once per county because BLS sub-county area codes are opaque and
non-deterministic.

So this job fetches each of NJ's 21 counties exactly once, and applies the
result to every Location whose county matches. Two measures (unemployment
rate, employment) across 21 counties is 42 series in a handful of batched
requests, well inside the free-tier limit, and it makes the "countywide"
label in the data literally true rather than an approximation.

Requires seed_locations.py to have run first, since it needs Location rows
with county already populated.

Usage:
    export BLS_API_KEY=your_key_here
    python -m ingestion.fetch_bls_batch --start-year 2019 --end-year 2023
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from app.database import SessionLocal
from app import models
from app.nj_counties import NJ_COUNTIES, laus_series_id

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Labels carry "(Countywide)" because these values ARE county figures
# applied to every municipality in that county. Without the label, a
# township of 24,000 people displays an employment figure of 300,000 and
# reads as its own workforce, which is how this surfaced as a bug report.
#
# The countywide approach is the deliberate tradeoff already documented in
# the methodology corpus: BLS sub-county area codes are opaque and
# non-deterministic, so a county figure with an honest label beats a
# municipal figure that is quietly wrong. But the label is what makes the
# tradeoff honest, and it was missing.
MEASURE_CODE_MAP = {
    "03": ("unemployment_rate", "Unemployment Rate (Countywide)", "%", "employment"),
    "05": ("employment", "Employment (Countywide)", "count", "employment"),
}

# BLS caps unregistered requests at 25 series per call and registered at 50.
# 21 counties x 2 measures = 42 series, so this fits in one registered call.
_BATCH_SIZE = 50


def fetch_series(series_ids: list[str], start_year: int, end_year: int, api_key: str) -> list[dict]:
    results = []
    for start in range(0, len(series_ids), _BATCH_SIZE):
        batch = series_ids[start:start + _BATCH_SIZE]
        resp = requests.post(
            BLS_API_URL,
            json={
                "seriesid": batch,
                "startyear": str(start_year),
                "endyear": str(end_year),
                "registrationkey": api_key,
                "annualaverage": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS API error: {data.get('message', data)}")
        results.extend(data["Results"]["series"])
    return results


def parse_annual_values(series: dict) -> dict[int, float]:
    """Keep only the M13 (annual average) datapoint per year, which is
    what makes county-level LAUS comparable to ACS 5-year figures instead
    of a single volatile month."""
    out = {}
    for item in series["data"]:
        if item["period"] == "M13":
            out[int(item["year"])] = float(item["value"])
    return out


def upsert(db, county_fips: str, measure_code: str, values_by_year: dict[int, float],
           existing_by_key: dict | None = None, pending_inserts: list | None = None) -> int:
    """Apply one county's series to every municipality in that county.

    Existing rows are looked up in a dictionary passed in by the caller
    rather than queried per row. A full run writes county figures to all 564
    municipalities across two measures and five years, which is over 5,000
    observations; querying each one separately is thousands of round trips
    to a hosted database and takes minutes rather than seconds.
    """
    mapping = MEASURE_CODE_MAP.get(measure_code)
    if not mapping:
        return 0
    metric_key, label, unit, category = mapping
    county_name = NJ_COUNTIES.get(county_fips)
    if not county_name:
        return 0

    locations = db.query(models.Location).filter(
        models.Location.state == "NJ", models.Location.county == county_name,
    ).all()
    if not locations:
        print(f"  No locations found for {county_name} County, skipping "
              f"(run seed_locations.py first).")
        return 0

    source = f"Bureau of Labor Statistics, LAUS ({county_name} County)"
    count = 0

    for location in locations:
        for year, value in values_by_year.items():
            key = (location.id, metric_key, year)
            existing = existing_by_key.get(key) if existing_by_key is not None else None
            if existing:
                existing.value = value
                existing.provenance = "measured"
                # Older rows predate the countywide label, so bring them up
                # to date rather than leaving a mix across the series.
                existing.label = label
                existing.source = source
            else:
                pending_inserts.append(dict(
                    location_id=location.id, category=category, metric_key=metric_key,
                    label=label, unit=unit, value=value, period=year,
                    source=source, source_url="https://www.bls.gov/lau/",
                    provenance="measured",
                ))
            count += 1
    return count


def run(start_year: int, end_year: int, api_key: str):
    id_to_key = {
        laus_series_id(county_fips, measure): (county_fips, measure)
        for county_fips in NJ_COUNTIES
        for measure in MEASURE_CODE_MAP
    }
    series_ids = list(id_to_key.keys())

    print(f"Fetching {len(series_ids)} series ({len(NJ_COUNTIES)} counties "
          f"x {len(MEASURE_CODE_MAP)} measures), {start_year}-{end_year}...")
    series_list = fetch_series(series_ids, start_year, end_year, api_key)

    db = SessionLocal()
    total = 0
    try:
        metric_keys = {m[0] for m in MEASURE_CODE_MAP.values()}
        periods = set(range(start_year, end_year + 1))

        # One query covering everything this run could collide with, rather
        # than one per observation.
        existing_rows = (
            db.query(models.Metric)
            .filter(
                models.Metric.metric_key.in_(metric_keys),
                models.Metric.period.in_(periods),
            )
            .all()
        )
        existing_by_key = {
            (m.location_id, m.metric_key, m.period): m for m in existing_rows
        }
        print(f"  {len(existing_rows):,} existing rows loaded for comparison")

        pending_inserts: list[dict] = []
        for series in series_list:
            key = id_to_key.get(series["seriesID"])
            if not key:
                continue
            county_fips, measure_code = key
            values = parse_annual_values(series)
            total += upsert(db, county_fips, measure_code, values,
                            existing_by_key, pending_inserts)

        if pending_inserts:
            db.bulk_insert_mappings(models.Metric, pending_inserts)
        db.commit()
        print(f"  {len(pending_inserts):,} inserted, "
              f"{total - len(pending_inserts):,} updated")
    finally:
        db.close()

    print(f"Upserted {total:,} observations across {len(NJ_COUNTIES)} counties.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    args = parser.parse_args()

    key = os.getenv("BLS_API_KEY")
    if not key:
        raise SystemExit("Set BLS_API_KEY in your environment first.")

    run(args.start_year, args.end_year, key)