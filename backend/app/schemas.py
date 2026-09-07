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
    # The period each change was actually measured from. Differs from
    # latest_period minus N when the exact year was missing and the nearest
    # earlier observation was used instead.
    baseline_1y_period: Optional[int] = None
    baseline_3y_period: Optional[int] = None
    baseline_5y_period: Optional[int] = None
    history: list[MetricPoint]
    source: Optional[str] = None


class MetricCoverage(BaseModel):
    """How much of the composite actually had data behind it. Two scores are
    only comparable when their coverage is comparable."""
    metrics_used: int
    metrics_total: int
    weight_covered: float
    missing_metrics: list[str] = []


class HeadlineChange(BaseModel):
    metric_key: str
    label: str
    change_3y_pct: float
    baseline_period: Optional[int] = None
    latest_period: Optional[int] = None


class AreaReport(BaseModel):
    location: LocationOut
    growth_score: float
    growth_score_label: str
    metric_coverage: MetricCoverage
    categories: dict[str, list[MetricSeries]]
    headline_changes: list[HeadlineChange]


class CompareRow(BaseModel):
    location: LocationOut
    growth_score: float
    metric_coverage: MetricCoverage
    metrics: dict[str, Optional[float]]  


class CompareResponse(BaseModel):
    metric_keys: list[str]
    rows: list[CompareRow]


class Citation(BaseModel):
    chunk_id: str
    kind: str
    fips: Optional[str] = None
    location_name: Optional[str] = None
    category: Optional[str] = None
    metric_keys: list[str] = []
    periods: list[int] = []
    sources: list[str] = []
    source_urls: list[str] = []
    provenance: object = None
    score: Optional[float] = None


class RetrievalTrace(BaseModel):
    used: bool
    chunks: list[str] = []
    top_score: Optional[float] = None
    generator: Optional[str] = None


class ResolvedPlaceOut(BaseModel):
    fips: str
    name: str


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    intent: str
    answer: str
    grounded: bool
    citations: list[Citation]
    resolved_places: list[ResolvedPlaceOut]
    provenance: str
    # Offered when a question can't be answered, so a refusal points
    # somewhere instead of just closing the door.
    suggestions: list[str] = []
    retrieval: RetrievalTrace


class CorpusStats(BaseModel):
    total_chunks: int
    by_kind: dict[str, int]
    embedding_provider: list[str]
    pgvector_enabled: bool