from pydantic import BaseModel
from typing import Optional


class LocationOut(BaseModel):
    id: int
    fips: str
    name: str
    state: str
    county: Optional[str] = None
    location_type: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        from_attributes = True


class MetricPoint(BaseModel):
    period: int
    value: float


class MetricSeries(BaseModel):
    category: str
    metric_key: str
    label: str
    unit: Optional[str] = None
    latest_value: float
    latest_period: int
    change_1y_pct: Optional[float] = None
    change_3y_pct: Optional[float] = None
    change_5y_pct: Optional[float] = None
    history: list[MetricPoint]
    source: Optional[str] = None


class AreaReport(BaseModel):
    location: LocationOut
    growth_score: float
    growth_score_label: str
    categories: dict[str, list[MetricSeries]]
    headline_changes: list[str]


class CompareRow(BaseModel):
    location: LocationOut
    growth_score: float
    metrics: dict[str, Optional[float]]  


class CompareResponse(BaseModel):
    metric_keys: list[str]
    rows: list[CompareRow]
