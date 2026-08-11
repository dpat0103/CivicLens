from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, UniqueConstraint, Text
)
from sqlalchemy.orm import relationship
from .database import Base


class Location(Base):
    """A city, county, or ZIP that we track. FIPS is the canonical
    geographic key that all metric sources get normalized to."""

    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    fips = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    state = Column(String(2), nullable=False)
    county = Column(String(120), nullable=True)
    location_type = Column(String(20), nullable=False, default="city")  # city | county | zip
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    metrics = relationship("Metric", back_populates="location", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("fips", name="uq_location_fips"),)


class Metric(Base):
    """A single (location, metric, year) observation, stored in
    long/tall format so new metrics/sources can be added without
    schema migrations."""

    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    category = Column(String(30), nullable=False, index=True)   # housing | employment | safety | transportation | population
    metric_key = Column(String(60), nullable=False, index=True)  # e.g. median_rent, unemployment_rate
    label = Column(String(120), nullable=False)                  # human readable, e.g. "Median Rent"
    unit = Column(String(20), nullable=True)                     # $, %, min, count
    value = Column(Float, nullable=False)
    period = Column(Integer, nullable=False, index=True)         # year, e.g. 2025

    source = Column(String(120), nullable=True)                  # e.g. "US Census ACS"
    source_url = Column(Text, nullable=True)

    location = relationship("Location", back_populates="metrics")

    __table_args__ = (
        UniqueConstraint("location_id", "metric_key", "period", name="uq_metric_obs"),
    )
