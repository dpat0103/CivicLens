"""
Real ingestion job: Bureau of Labor Statistics Local Area Unemployment
Statistics (LAUS) -- COUNTY level.

Why county, not city?
----------------------
BLS LAUS *city-level* data uses BLS's own internal "area codes" with
no deterministic formula (unlike Census, which uses a clean state+place
FIPS scheme). There's no reliable way to compute a city's series ID --
you'd need to look each one up individually against BLS's area
reference file, and even city-level LAUS data, when available, is only
published not-seasonally-adjusted with looser reliability standards
than county/state data. (A comparable open-source LAUS fetcher project
we checked had discontinued their city-level fetcher for this exact
reason.)

County-level series IDs, by contrast, are fully deterministic:
    LA + U + CN + <state fips, 2> + <county fips, 3> + 00000000 + <measure code, 2>
e.g. Hudson County, NJ unemployment rate = LAUCN340170000000003

So this job pulls county-level employment and unemployment, and
applies each county's figures to every seeded Location in that county
(we already store `county` on each Location). This is a standard,
honest simplification -- city-level employment isn't usually available
cleanly, so reporting the surrounding county's labor market is a
normal thing to do. The Metric `label` and `source` fields say
"(Countywide)" so nothing is presented as more precise than it is.

Get a free API key (raises rate limits from 25/day to 500/day and
unlocks annual averages): https://data.bls.gov/registrationEngine/

Usage:
    $env:BLS_API_KEY = "your_key_here"     # PowerShell
    python -m ingestion.fetch_bls --start-year 2021 --end-year 2023

Docs: https://www.bls.gov/help/hlpforma.htm#LA
      https://www.bls.gov/developers/api_signature_v2.htm
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv
from app.database import SessionLocal
from app import models

load_dotenv()  # picks up backend/.env, so BLS_API_KEY only needs to be set once

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# NJ county name -> 3-digit county FIPS. Verified against the Census
# Bureau's standard county FIPS list. Only counties present in our
# seeded pilot locations are listed; add more here if the pilot
# expands to other NJ counties.
NJ_COUNTY_FIPS = {
    "Bergen": "003",
    "Camden": "007",
    "Essex": "013",
    "Hudson": "017",
    "Mercer": "021",
    "Middlesex": "023",
    "Monmouth": "025",
    "Morris": "027",
    "Union": "039",
}

MEASURE_CODE_MAP = {
    "03": ("unemployment_rate", "Unemployment Rate (Countywide)", "%", "employment"),
    "05": ("employment", "Employment (Countywide)", "count", "employment"),
}


def build_series_id(state_fips: str, county_fips: str, measure_code: str) -> str:
    """LAUCN<state fips 2><county fips 3>00000000<measure code 2> = 20 chars."""
    return f"LAUCN{state_fips}{county_fips}00000000{measure_code}"


def fetch_county_series(county_fips_map: dict, start_year: int, end_year: int,
                         api_key: str, state_fips: str = "34") -> dict:
    """Returns {county_name: {metric_key: {year: value}}}"""
    series_id_to_county = {}
    series_ids = []
    for county_name, county_fips in county_fips_map.items():
        for measure_code in MEASURE_CODE_MAP:
            sid = build_series_id(state_fips, county_fips, measure_code)
            series_id_to_county[sid] = (county_name, measure_code)
            series_ids.append(sid)

    # BLS v2 API accepts up to 50 series per request with a registration key.
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
        raise RuntimeError(f"BLS API error: {data.get('message', data)}")

    results: dict = {}
    for series in data["Results"]["series"]:
        sid = series["seriesID"]
        if sid not in series_id_to_county:
            continue
        county_name, measure_code = series_id_to_county[sid]
        metric_key = MEASURE_CODE_MAP[measure_code][0]

        for item in series["data"]:
            if item["period"] != "M13":  # M13 = annual average
                continue
            year = int(item["year"])
            value = float(item["value"])
            results.setdefault(county_name, {}).setdefault(metric_key, {})[year] = value

    return results


def upsert(db, county_data: dict, period_years: list[int]):
    locations = db.query(models.Location).filter(models.Location.state == "NJ").all()

    matched, updated = 0, 0
    for location in locations:
        county_metrics = county_data.get(location.county)
        if not county_metrics:
            print(f"  No BLS data found for {location.name}'s county ({location.county}) -- skipping.")
            continue

        matched += 1
        for measure_code, (metric_key, label, unit, category) in MEASURE_CODE_MAP.items():
            values_by_year = county_metrics.get(metric_key, {})
            for year in period_years:
                if year not in values_by_year:
                    continue
                value = values_by_year[year]

                existing = (
                    db.query(models.Metric)
                    .filter_by(location_id=location.id, metric_key=metric_key, period=year)
                    .first()
                )
                if existing:
                    # Update everything, not just value -- a pre-existing row
                    # is almost always the seeded mock metric, and its label/
                    # source need to change too or the UI keeps showing the
                    # old mock provenance even once the number itself is real.
                    existing.value = value
                    existing.label = label
                    existing.unit = unit
                    existing.category = category
                    existing.source = "Bureau of Labor Statistics, LAUS (county-level)"
                    existing.source_url = "https://www.bls.gov/lau/"
                else:
                    db.add(models.Metric(
                        location_id=location.id, category=category, metric_key=metric_key,
                        label=label, unit=unit, value=value, period=year,
                        source="Bureau of Labor Statistics, LAUS (county-level)",
                        source_url="https://www.bls.gov/lau/",
                    ))
                updated += 1

    db.commit()
    print(f"Matched {matched}/{len(locations)} locations to a county with BLS data. "
          f"Upserted {updated} metric observations.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--state", default="34", help="State FIPS code, default 34 = New Jersey")
    args = parser.parse_args()

    key = os.getenv("BLS_API_KEY")
    if not key:
        raise SystemExit("Set BLS_API_KEY in your environment first.")

    print(f"Fetching county-level LAUS data for {len(NJ_COUNTY_FIPS)} NJ counties, "
          f"{args.start_year}-{args.end_year}...")
    county_data = fetch_county_series(NJ_COUNTY_FIPS, args.start_year, args.end_year, key, args.state)

    db = SessionLocal()
    try:
        upsert(db, county_data, list(range(args.start_year, args.end_year + 1)))
    finally:
        db.close()