from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, scoring
from .locations import _location_series

router = APIRouter(prefix="/compare", tags=["compare"])

# The metrics shown as columns in the comparison table, in display order.
COMPARE_METRIC_KEYS = [
    "median_rent",
    "population",
    "employment",
    "unemployment_rate",
    "median_household_income",
    "new_housing_permits",
    "property_crime_rate",
    "violent_crime_rate",
    "avg_commute_minutes",
]


@router.get("", response_model=schemas.CompareResponse)
def compare_locations(
    fips: list[str] = Query(..., description="Repeatable query param, e.g. ?fips=3403919000&fips=3401736080"),
    db: Session = Depends(get_db),
):
    if len(fips) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 fips codes to compare")
    if len(fips) > 6:
        raise HTTPException(status_code=400, detail="Compare supports at most 6 locations at once")

    rows = []
    for code in fips:
        location = db.query(models.Location).filter(models.Location.fips == code).first()
        if not location:
            raise HTTPException(status_code=404, detail=f"No location found for fips '{code}'")

        series_by_key = _location_series(db, location)
        score, _ = scoring.compute_growth_score(series_by_key)

        metrics = {}
        for key in COMPARE_METRIC_KEYS:
            series = series_by_key.get(key)
            metrics[key] = series["latest_value"] if series else None

        rows.append({"location": location, "growth_score": score, "metrics": metrics})

    return {"metric_keys": COMPARE_METRIC_KEYS, "rows": rows}
