"""Deterministic fixture municipalities for the test suite.

Shaped like the real ingestion output rather than the demo seed: the same
fifteen metric keys, labels, units and categories that fetch_census.py and
fetch_bls_batch.py write, ACS years 2019-2023, everything marked measured,
and employment shared across each county the way BLS LAUS data is.

The set is chosen to exercise the cases that broke on real data:
duplicate names disambiguated by county (two Washington Townships, two
Franklin Townships), a name that is a substring of another (Union and
Union City), place names containing metric words (Trenton contains "rent"),
and pairs of towns in the same county that share employment figures.
"""

from app import models

YEARS = [2019, 2020, 2021, 2022, 2023]

ACS = ("US Census ACS 5-Year Estimates", "https://www.census.gov/programs-surveys/acs")


def _laus(county: str):
    return (f"Bureau of Labor Statistics, LAUS ({county} County)", "https://www.bls.gov/lau/")


# name, fips, county, then 2023 values and an annual growth rate for the
# indicators that move. Values are deliberately not round so a test can
# tell a real figure from an invented one.
TOWNS = [
    (
        "Montclair",
        "3401347500",
        "Essex",
        dict(pop=40128, income=153231, rent=2041, home=812400, growth=0.012),
    ),
    (
        "Bloomfield",
        "3401306260",
        "Essex",
        dict(pop=53105, income=98764, rent=1712, home=438900, growth=0.009),
    ),
    ("Newark", "3401351000", "Essex", dict(pop=307355, income=46460, rent=1268, home=331700, growth=0.004)),
    ("Hoboken", "3401732250", "Hudson", dict(pop=58690, income=176074, rent=2689, home=877300, growth=0.015)),
    ("Bayonne", "3401703580", "Hudson", dict(pop=70553, income=84117, rent=1497, home=436200, growth=0.007)),
    (
        "Jersey City",
        "3401736000",
        "Hudson",
        dict(pop=287899, income=91151, rent=1737, home=516900, growth=0.011),
    ),
    (
        "Union City",
        "3401774630",
        "Hudson",
        dict(pop=67258, income=61421, rent=1394, home=388400, growth=0.003),
    ),
    ("Union", "3403974480", "Union", dict(pop=59325, income=103911, rent=1683, home=473600, growth=0.006)),
    (
        "Princeton",
        "3402160900",
        "Mercer",
        dict(pop=30681, income=186030, rent=2318, home=1073800, growth=0.008),
    ),
    ("Trenton", "3402174000", "Mercer", dict(pop=90055, income=40915, rent=1118, home=134900, growth=-0.002)),
    ("Camden", "3400710000", "Camden", dict(pop=71799, income=33103, rent=1003, home=106700, growth=-0.004)),
    (
        "Washington Township (Morris County)",
        "3402777180",
        "Morris",
        dict(pop=18537, income=176944, rent=2097, home=691200, growth=0.005),
    ),
    (
        "Washington Township (Warren County)",
        "3404177240",
        "Warren",
        dict(pop=6559, income=110867, rent=1352, home=331400, growth=0.003),
    ),
    (
        "Franklin Township (Somerset County)",
        "3403524990",
        "Somerset",
        dict(pop=68364, income=124373, rent=1959, home=479500, growth=0.010),
    ),
    (
        "Franklin Township (Hunterdon County)",
        "3401924840",
        "Hunterdon",
        dict(pop=3239, income=163125, rent=1611, home=581300, growth=0.002),
    ),
]

# Countywide BLS figures for 2023, with an annual growth rate. Every town in
# a county gets the same series, which is what the employment methodology
# note explains.
COUNTY_EMPLOYMENT = {
    "Essex": (391247, 0.011, 5.4),
    "Hudson": (351011, 0.008, 4.6),
    "Union": (282946, 0.009, 4.9),
    "Mercer": (190288, 0.006, 4.1),
    "Camden": (255319, 0.007, 4.8),
    "Morris": (268716, 0.010, 3.5),
    "Warren": (54012, 0.004, 4.0),
    "Somerset": (176993, 0.012, 3.6),
    "Hunterdon": (66841, 0.005, 3.4),
}


def _backcast(latest: float, rate: float, digits: int) -> dict[int, float]:
    """Values for every year, ending at `latest` in 2023."""
    out = {}
    for year in YEARS:
        out[year] = round(latest / ((1 + rate) ** (2023 - year)), digits)
        if digits == 0:
            out[year] = float(int(out[year]))
    return out


def _town_metrics(index: int, county: str, v: dict) -> list[dict]:
    g = v["growth"]
    # Derived indicators vary by town without needing a column each.
    derived = dict(
        median_age=(35.2 + index * 0.7, 0.002, 1, "years", "Median Age", "population"),
        per_capita_income=(round(v["income"] * 0.58), g + 0.01, 0, "$", "Per Capita Income", "population"),
        poverty_rate=(
            round(4.1 + (200000 - v["income"]) / 9000, 1),
            -0.01,
            1,
            "%",
            "Poverty Rate",
            "population",
        ),
        bachelors_or_higher_pct=(
            round(18 + v["income"] / 3200, 1),
            0.01,
            1,
            "%",
            "Bachelor's Degree or Higher",
            "population",
        ),
        rent_burden_pct=(round(26 + index * 0.6, 1), 0.004, 1, "%", "Rent as % of Income", "housing"),
        homeownership_rate=(round(30 + (index * 3.3) % 45, 1), 0.0, 1, "%", "Homeownership Rate", "housing"),
        vacancy_rate=(round(4.5 + (index * 0.9) % 6, 1), -0.01, 1, "%", "Housing Vacancy Rate", "housing"),
        avg_commute_minutes=(
            round(26.4 + (index * 1.7) % 14, 1),
            0.005,
            1,
            "min",
            "Average Commute",
            "transportation",
        ),
        transit_commute_pct=(
            round(3.2 + (index * 4.1) % 38, 1),
            0.01,
            1,
            "%",
            "Commute by Public Transit",
            "transportation",
        ),
    )
    direct = dict(
        population=(v["pop"], g, 0, "count", "Population", "population"),
        median_household_income=(v["income"], g + 0.02, 0, "$", "Median Household Income", "population"),
        median_rent=(v["rent"], 0.035, 0, "$", "Median Rent", "housing"),
        median_home_value=(v["home"], 0.05, 0, "$", "Median Home Value", "housing"),
    )

    rows = []
    for key, (latest, rate, digits, unit, label, category) in {**direct, **derived}.items():
        for year, value in _backcast(latest, rate, digits).items():
            rows.append(
                dict(
                    category=category,
                    metric_key=key,
                    label=label,
                    unit=unit,
                    value=value,
                    period=year,
                    source=ACS[0],
                    source_url=ACS[1],
                    provenance="measured",
                )
            )

    employed, emp_rate, unemployment = COUNTY_EMPLOYMENT[county]
    src, url = _laus(county)
    for year, value in _backcast(employed, emp_rate, 0).items():
        rows.append(
            dict(
                category="employment",
                metric_key="employment",
                label="Employment (Countywide)",
                unit="count",
                value=value,
                period=year,
                source=src,
                source_url=url,
                provenance="measured",
            )
        )
    for year, value in _backcast(unemployment, -0.03, 1).items():
        rows.append(
            dict(
                category="employment",
                metric_key="unemployment_rate",
                label="Unemployment Rate (Countywide)",
                unit="%",
                value=value,
                period=year,
                source=src,
                source_url=url,
                provenance="measured",
            )
        )
    return rows


def populate(db) -> None:
    for index, (name, fips, county, values) in enumerate(TOWNS):
        location = models.Location(fips=fips, name=name, state="NJ", county=county, location_type="city")
        db.add(location)
        db.flush()
        for row in _town_metrics(index, county, values):
            db.add(models.Metric(location_id=location.id, **row))
    db.commit()
