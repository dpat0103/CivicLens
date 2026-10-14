"""
Diagnostic: print the raw Census NAME field for any NJ place containing
'Montclair' or 'Princeton', so we can see exactly how the API labels
them and fix the name-matching regex if needed.

Kept for reference: it queries the Census place endpoint, which ingestion
no longer uses (seed_locations.py explains why county subdivisions
replaced it).

Usage, from backend/:
    CENSUS_API_KEY=your-key python scripts/diagnose_census_names.py
"""

import os
import requests

key = os.getenv("CENSUS_API_KEY")
if not key:
    raise SystemExit("Set CENSUS_API_KEY first.")

params = {
    "get": "NAME",
    "for": "place:*",
    "in": "state:34",
    "key": key,
}
resp = requests.get("https://api.census.gov/data/2023/acs/acs5", params=params, timeout=30)
resp.raise_for_status()
data = resp.json()

header, *records = data
name_idx = header.index("NAME")

for row in records:
    name = row[name_idx]
    if "montclair" in name.lower() or "princeton" in name.lower():
        print(repr(name))
