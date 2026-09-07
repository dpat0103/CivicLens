"""
New Jersey county reference data.

Static, not fetched. NJ's 21 counties and their FIPS codes have been fixed
since 1970 and won't change during this project's lifetime, so this is
reference data of the same character as state postal abbreviations, not
something to fetch and cache.

Codes are the 3-digit county FIPS as used in the second half of a full
5-digit county FIPS (34 + this code), and in BLS LAUS series IDs.
"""

NJ_COUNTIES: dict[str, str] = {
    "001": "Atlantic",
    "003": "Bergen",
    "005": "Burlington",
    "007": "Camden",
    "009": "Cape May",
    "011": "Cumberland",
    "013": "Essex",
    "015": "Gloucester",
    "017": "Hudson",
    "019": "Hunterdon",
    "021": "Mercer",
    "023": "Middlesex",
    "025": "Monmouth",
    "027": "Morris",
    "029": "Ocean",
    "031": "Passaic",
    "033": "Salem",
    "035": "Somerset",
    "037": "Sussex",
    "039": "Union",
    "041": "Warren",
}

# Reverse lookup: county name (lowercase, no "County" suffix) -> FIPS code.
COUNTY_NAME_TO_FIPS: dict[str, str] = {
    name.lower(): fips for fips, name in NJ_COUNTIES.items()
}


def county_fips_for_name(county_name: str | None) -> str | None:
    """'Essex' or 'Essex County' -> '013'. None if not recognized."""
    if not county_name:
        return None
    cleaned = county_name.strip().lower().removesuffix(" county").strip()
    return COUNTY_NAME_TO_FIPS.get(cleaned)


def laus_series_id(county_fips: str, measure_code: str) -> str:
    """Build a BLS LAUS series ID for an NJ county.

    Format: LAUCN + state fips (2) + county fips (3) + 00000000 (8) + measure (2)
    = 20 characters. NJ state FIPS is 34.

    Verified against the example already documented in fetch_bls.py:
    LAUCN340170000000003 for Bergen County (034) unemployment rate (03).
    """
    return f"LAUCN34{county_fips}00000000{measure_code}"


assert laus_series_id("017", "03") == "LAUCN340170000000003"  # Hudson, from fetch_bls.py's own docstring
