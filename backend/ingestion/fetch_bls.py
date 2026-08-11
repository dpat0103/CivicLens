"""
Real ingestion job: Bureau of Labor Statistics Local Area Unemployment
Statistics (LAUS).

Template only, same reasoning as fetch_census.py -- wire this in once
you have a BLS API key and are ready to move a metro/city off sample
data and onto live figures.

Get a free key (raises rate limits from 25/day to 500/day):
https://data.bls.gov/registrationEngine/

LAUS series ID format: LAUCN<state+county fips><measure code>
  measure 03 = unemployment rate, 04 = unemployed, 05 = employed, 06 = labor force
Docs: https://www.bls.gov/help/hlpforma.htm#LA

Usage:
    export BLS_API_KEY=your_key_here
    python -m ingestion.fetch_bls --series LAUCN340170000000003 --start-year 2021 --end-year 2025
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from app.database import SessionLocal
from app import models

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

MEASURE_CODE_MAP = {
    "03": ("unemployment_rate", "Unemployment Rate", "%", "employment"),
    "05": ("employment", "Employment", "count", "employment"),
}


def fetch_series(series_ids: list[str], start_year: int, end_year: int, api_key: str) -> dict:
    payload = {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
        "registrationkey": api_key,
        "annualaverage": True,
    }
    resp = requests.post(BLS_API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API error: {data}")
    return data["Results"]["series"]


def upsert(db, location_fips: str, series_list: list[dict]):
    location = db.query(models.Location).filter(models.Location.fips == location_fips).first()
    if not location:
        print(f"No matching Location for fips {location_fips}, skipping. "
              f"Add it to seed_data.MUNICIPALITIES first.")
        return

    count = 0
    for series in series_list:
        measure_code = series["seriesID"][-2:]
        mapping = MEASURE_CODE_MAP.get(measure_code)
        if not mapping:
            continue
        metric_key, label, unit, category = mapping

        for item in series["data"]:
            if item["period"] != "M13":  # M13 = annual average
                continue
            year = int(item["year"])
            value = float(item["value"])

            existing = (
                db.query(models.Metric)
                .filter_by(location_id=location.id, metric_key=metric_key, period=year)
                .first()
            )
            if existing:
                existing.value = value
            else:
                db.add(models.Metric(
                    location_id=location.id, category=category, metric_key=metric_key,
                    label=label, unit=unit, value=value, period=year,
                    source="Bureau of Labor Statistics, LAUS", source_url="https://www.bls.gov/lau/",
                ))
            count += 1
    db.commit()
    print(f"Upserted {count} BLS metric observations for {location.name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fips", required=True, help="Our internal Location fips to attach results to")
    parser.add_argument("--series", nargs="+", required=True, help="One or more BLS LAUS series IDs")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    args = parser.parse_args()

    key = os.getenv("BLS_API_KEY")
    if not key:
        raise SystemExit("Set BLS_API_KEY in your environment first.")

    series_list = fetch_series(args.series, args.start_year, args.end_year, key)
    db = SessionLocal()
    try:
        upsert(db, args.fips, series_list)
    finally:
        db.close()
