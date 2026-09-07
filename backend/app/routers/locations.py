from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database import get_db
from .. import models, schemas, scoring

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[schemas.LocationOut])
def list_locations(
    q: str | None = Query(None, description="Search by name, state, or FIPS"),
    db: Session = Depends(get_db),
):
    query = db.query(models.Location)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                models.Location.name.ilike(like),
                models.Location.state.ilike(like),
                models.Location.fips.ilike(like),
            )
        )
    return query.order_by(models.Location.name).all()


def _location_series(db: Session, location: models.Location) -> dict:
    """Build metric_key -> series dict for a location."""
    rows = (
        db.query(models.Metric)
        .filter(models.Metric.location_id == location.id)
        .order_by(models.Metric.period)
        .all()
    )
    grouped = defaultdict(list)
    meta = {}
    for r in rows:
        grouped[r.metric_key].append((r.period, r.value))
        meta[r.metric_key] = r

    series_by_key = {}
    for key, points in grouped.items():
        m = meta[key]
        series_by_key[key] = scoring.build_series(
            points, m.category, key, m.label, m.unit, m.source
        )
    return series_by_key


@router.get("/{fips}/report", response_model=schemas.AreaReport)
def get_area_report(fips: str, db: Session = Depends(get_db)):
    location = db.query(models.Location).filter(models.Location.fips == fips).first()
    if not location:
        raise HTTPException(status_code=404, detail=f"No location found for fips '{fips}'")

    series_by_key = _location_series(db, location)
    if not series_by_key:
        raise HTTPException(status_code=404, detail="No metric data ingested for this location yet")

    score, label, coverage = scoring.compute_growth_score(series_by_key)
    changes = scoring.headline_changes(series_by_key)

    categories: dict[str, list[dict]] = defaultdict(list)
    for series in series_by_key.values():
        categories[series["category"]].append(series)
    for cat in categories:
        categories[cat].sort(key=lambda s: s["label"])

    return {
        "location": location,
        "growth_score": score,
        "growth_score_label": label,
        "metric_coverage": coverage,
        "categories": categories,
        "headline_changes": changes,
    }