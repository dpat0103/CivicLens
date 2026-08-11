"""
Seed the database with a V1 pilot dataset: ~15 New Jersey municipalities,
5 years of history (2021-2025), across the four MVP dimensions
(housing, employment, safety, population) plus transportation.

Why seed data instead of live API calls?
-----------------------------------------
This repo ships two things:
  1. This seed script -- deterministic, realistic sample data so the
     app runs end-to-end with zero API keys and zero setup friction.
  2. `fetch_census.py` / `fetch_bls.py` -- real ingestion jobs that hit
     the live Census and BLS APIs. Wire those in (see their docstrings
     for the free API key signup) to replace the sample data with real
     pulls once you're ready to expand past the pilot.

Run with:  python -m ingestion.seed_data
"""
import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, SessionLocal
from app import models

YEARS = [2021, 2022, 2023, 2024, 2025]
SOURCE_MAP = {
    "population": ("US Census ACS 5-Year Estimates", "https://www.census.gov/programs-surveys/acs"),
    "median_household_income": ("US Census ACS 5-Year Estimates", "https://www.census.gov/programs-surveys/acs"),
    "median_rent": ("US Census ACS 5-Year Estimates", "https://www.census.gov/programs-surveys/acs"),
    "new_housing_permits": ("US Census Building Permits Survey", "https://www.census.gov/construction/bps/"),
    "employment": ("Bureau of Labor Statistics, LAUS", "https://www.bls.gov/lau/"),
    "unemployment_rate": ("Bureau of Labor Statistics, LAUS", "https://www.bls.gov/lau/"),
    "property_crime_rate": ("NJ State Police UCR-SRS", "https://www.njsp.org/ucr/"),
    "violent_crime_rate": ("NJ State Police UCR-SRS", "https://www.njsp.org/ucr/"),
    "avg_commute_minutes": ("US Census ACS 5-Year Estimates", "https://www.census.gov/programs-surveys/acs"),
    "transit_ridership_index": ("NJ Transit Open Data", "https://www.njtransit.com/open-data"),
}

# (name, fips, county, base_population, pop_growth_rate/yr, base_rent,
#  rent_growth_rate/yr, base_income, income_growth_rate/yr,
#  base_unemployment_pct, employment_growth_rate/yr, base_permits/yr,
#  permits_growth_rate/yr, base_property_crime, crime_trend/yr,
#  base_violent_crime, violent_trend/yr, base_commute_min, commute_trend/yr)
MUNICIPALITIES = [
    dict(name="Jersey City", fips="3403919000", county="Hudson", lat=40.7178, lng=-74.0431,
         pop=292000, pop_g=0.019, rent=2650, rent_g=0.068, income=85000, income_g=0.045,
         unemp=4.4, unemp_trend=-0.15, emp=155000, emp_g=0.017, permits=1900, permits_g=0.09,
         prop_crime=18.2, prop_trend=-0.04, viol_crime=4.1, viol_trend=-0.03, commute=36, commute_g=0.005),
    dict(name="Hoboken", fips="3401736080", county="Hudson", lat=40.7439, lng=-74.0324,
         pop=59900, pop_g=0.011, rent=3050, rent_g=0.04, income=145000, income_g=0.035,
         unemp=3.2, unemp_trend=-0.1, emp=41000, emp_g=0.012, permits=380, permits_g=0.03,
         prop_crime=9.8, prop_trend=-0.08, viol_crime=1.6, viol_trend=-0.05, commute=31, commute_g=0.003),
    dict(name="Newark", fips="3403551000", county="Essex", lat=40.7357, lng=-74.1724,
         pop=311000, pop_g=0.008, rent=1780, rent_g=0.05, income=42000, income_g=0.038,
         unemp=7.1, unemp_trend=-0.2, emp=140000, emp_g=0.009, permits=1250, permits_g=0.05,
         prop_crime=21.4, prop_trend=-0.06, viol_crime=8.9, viol_trend=-0.04, commute=38, commute_g=0.004),
    dict(name="Montclair", fips="3404748900", county="Essex", lat=40.8259, lng=-74.2090,
         pop=40700, pop_g=0.006, rent=2350, rent_g=0.032, income=128000, income_g=0.03,
         unemp=3.0, unemp_trend=-0.08, emp=21000, emp_g=0.008, permits=140, permits_g=0.02,
         prop_crime=11.1, prop_trend=-0.03, viol_crime=1.9, viol_trend=-0.02, commute=34, commute_g=0.002),
    dict(name="New Brunswick", fips="3404150960", county="Middlesex", lat=40.4862, lng=-74.4518,
         pop=57400, pop_g=0.014, rent=1990, rent_g=0.047, income=48500, income_g=0.033,
         unemp=5.8, unemp_trend=-0.12, emp=34000, emp_g=0.014, permits=310, permits_g=0.06,
         prop_crime=17.6, prop_trend=-0.05, viol_crime=5.2, viol_trend=-0.03, commute=29, commute_g=0.001),
    dict(name="Elizabeth", fips="3404122000", county="Union", lat=40.6640, lng=-74.2107,
         pop=137300, pop_g=0.009, rent=1850, rent_g=0.044, income=52000, income_g=0.028,
         unemp=6.2, unemp_trend=-0.14, emp=58000, emp_g=0.01, permits=290, permits_g=0.04,
         prop_crime=19.9, prop_trend=-0.04, viol_crime=6.8, viol_trend=-0.03, commute=35, commute_g=0.003),
    dict(name="Trenton", fips="3404074000", county="Mercer", lat=40.2206, lng=-74.7597,
         pop=90200, pop_g=-0.003, rent=1420, rent_g=0.03, income=39000, income_g=0.02,
         unemp=7.8, unemp_trend=-0.1, emp=32000, emp_g=0.002, permits=95, permits_g=0.01,
         prop_crime=26.3, prop_trend=-0.02, viol_crime=11.4, viol_trend=-0.02, commute=27, commute_g=0.0),
    dict(name="Camden", fips="3400910000", county="Camden", lat=39.9259, lng=-75.1196,
         pop=71800, pop_g=-0.005, rent=1150, rent_g=0.025, income=32000, income_g=0.022,
         unemp=8.9, unemp_trend=-0.15, emp=24000, emp_g=0.001, permits=60, permits_g=0.01,
         prop_crime=29.8, prop_trend=-0.07, viol_crime=14.2, viol_trend=-0.06, commute=28, commute_g=0.0),
    dict(name="Princeton", fips="3405760955", county="Mercer", lat=40.3573, lng=-74.6672,
         pop=31200, pop_g=0.007, rent=2450, rent_g=0.03, income=142000, income_g=0.032,
         unemp=2.6, unemp_trend=-0.05, emp=19000, emp_g=0.009, permits=85, permits_g=0.02,
         prop_crime=7.5, prop_trend=-0.02, viol_crime=1.1, viol_trend=-0.01, commute=26, commute_g=0.0),
    dict(name="Morristown", fips="3404349430", county="Morris", lat=40.7968, lng=-74.4815,
         pop=20400, pop_g=0.01, rent=2150, rent_g=0.038, income=98000, income_g=0.03,
         unemp=3.4, unemp_trend=-0.07, emp=15000, emp_g=0.011, permits=110, permits_g=0.04,
         prop_crime=10.2, prop_trend=-0.03, viol_crime=1.8, viol_trend=-0.02, commute=33, commute_g=0.002),
    dict(name="Bayonne", fips="3400302990", county="Hudson", lat=40.6687, lng=-74.1143,
         pop=71700, pop_g=0.016, rent=1990, rent_g=0.055, income=76000, income_g=0.04,
         unemp=4.6, unemp_trend=-0.1, emp=27000, emp_g=0.014, permits=420, permits_g=0.11,
         prop_crime=13.4, prop_trend=-0.05, viol_crime=2.9, viol_trend=-0.03, commute=39, commute_g=0.004),
    dict(name="Union City", fips="3407679430", county="Hudson", lat=40.7795, lng=-74.0237,
         pop=69200, pop_g=0.004, rent=1720, rent_g=0.041, income=52500, income_g=0.026,
         unemp=5.3, unemp_trend=-0.1, emp=27500, emp_g=0.006, permits=90, permits_g=0.02,
         prop_crime=14.9, prop_trend=-0.03, viol_crime=3.6, viol_trend=-0.02, commute=37, commute_g=0.003),
    dict(name="Fort Lee", fips="3402725010", county="Bergen", lat=40.8509, lng=-73.9701,
         pop=39400, pop_g=0.003, rent=2550, rent_g=0.028, income=99000, income_g=0.025,
         unemp=3.6, unemp_trend=-0.06, emp=15000, emp_g=0.005, permits=60, permits_g=0.02,
         prop_crime=8.9, prop_trend=-0.02, viol_crime=1.2, viol_trend=-0.01, commute=32, commute_g=0.001),
    dict(name="Asbury Park", fips="3400302280", county="Monmouth", lat=40.2204, lng=-74.0121,
         pop=15200, pop_g=0.02, rent=2100, rent_g=0.07, income=58000, income_g=0.05,
         unemp=4.9, unemp_trend=-0.12, emp=6800, emp_g=0.02, permits=95, permits_g=0.12,
         prop_crime=16.8, prop_trend=-0.06, viol_crime=4.4, viol_trend=-0.05, commute=34, commute_g=0.002),
    dict(name="Hackensack", fips="3402730370", county="Bergen", lat=40.8859, lng=-74.0435,
         pop=46700, pop_g=0.009, rent=2050, rent_g=0.042, income=71000, income_g=0.03,
         unemp=4.2, unemp_trend=-0.09, emp=22000, emp_g=0.01, permits=150, permits_g=0.05,
         prop_crime=13.9, prop_trend=-0.04, viol_crime=2.7, viol_trend=-0.02, commute=33, commute_g=0.002),
]


def _series(base: float, annual_rate: float, years: list[int], noise: float, rng: random.Random) -> dict:
    """Project a metric backward/forward from a 2025 base value using a
    steady annual growth/decline rate, with a touch of realistic noise."""
    latest_year = max(years)
    out = {}
    for y in years:
        periods_back = latest_year - y
        value = base / ((1 + annual_rate) ** periods_back)
        value *= 1 + rng.uniform(-noise, noise)
        out[y] = round(value, 2)
    return out


def build_metric_rows(m: dict, rng: random.Random) -> list[dict]:
    rows = []

    def add(key, category, label, unit, base, rate, noise=0.01):
        series = _series(base, rate, YEARS, noise, rng)
        src, url = SOURCE_MAP[key]
        for year, value in series.items():
            rows.append(dict(category=category, metric_key=key, label=label, unit=unit,
                              value=value, period=year, source=src, source_url=url))

    add("population", "population", "Population", "count", m["pop"], m["pop_g"])
    add("median_household_income", "population", "Median Household Income", "$", m["income"], m["income_g"])
    add("median_rent", "housing", "Median Rent", "$", m["rent"], m["rent_g"])
    add("new_housing_permits", "housing", "New Housing Permits", "count", m["permits"], m["permits_g"], noise=0.05)
    add("employment", "employment", "Employment", "count", m["emp"], m["emp_g"])
    add("unemployment_rate", "employment", "Unemployment Rate", "%", m["unemp"], m["unemp_trend"], noise=0.03)
    add("property_crime_rate", "safety", "Property Crime Rate", "per 1,000", m["prop_crime"], m["prop_trend"], noise=0.03)
    add("violent_crime_rate", "safety", "Violent Crime Rate", "per 1,000", m["viol_crime"], m["viol_trend"], noise=0.04)
    add("avg_commute_minutes", "transportation", "Average Commute", "min", m["commute"], m["commute_g"], noise=0.01)
    add("transit_ridership_index", "transportation", "Transit Ridership Index", "index",
        100 * (1 + m["pop_g"] * 2), m["pop_g"] * 1.4, noise=0.04)

    return rows


def seed():
    rng = random.Random(42)  # deterministic so re-running gives identical data

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(models.Location).count()
        if existing:
            print(f"Database already has {existing} locations. Skipping seed. "
                  f"Delete civiclens.db first if you want to reseed.")
            return

        for m in MUNICIPALITIES:
            location = models.Location(
                fips=m["fips"], name=m["name"], state="NJ", county=m["county"],
                location_type="city", latitude=m["lat"], longitude=m["lng"],
            )
            db.add(location)
            db.flush()  # get location.id

            for row in build_metric_rows(m, rng):
                db.add(models.Metric(location_id=location.id, **row))

        db.commit()
        print(f"Seeded {len(MUNICIPALITIES)} municipalities x {len(YEARS)} years of metrics.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
