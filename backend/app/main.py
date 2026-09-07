"""CivicLens API.

Three groups of endpoints:

    /locations   municipality list, search, and per-municipality reports
    /compare     several municipalities side by side
    /ask         natural-language questions (see app.rag)

Table creation runs at import. That is fine for SQLite and for a schema this
small, but note that create_all() only creates missing tables and never
alters existing ones, so a column added to a model will not appear in a
database that already has that table. Schema changes therefore need a
migration; see ingestion/migrate_provenance.py for the pattern.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .database import Base, engine, get_db
from .routers import locations, compare, ask
from .rag import store as _rag_store  # noqa: F401  registers the rag_chunks table

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CivicLens API",
    description=(
        "Municipal statistics for New Jersey, normalised from US Census ACS "
        "and Bureau of Labor Statistics sources into comparable series."
    ),
    version="1.0.0",
)

# Origins come from the environment so local and deployed differ without a
# code change. The previous "*" was not just permissive: browsers reject a
# wildcard origin combined with allow_credentials, so that configuration was
# also broken for any credentialed request.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # No cookies or auth headers are used; the API is read-only and public.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(locations.router)
app.include_router(compare.router)
app.include_router(ask.router)


@app.get("/", tags=["health"])
def health():
    """Liveness and database reachability.

    Deliberately issues a query rather than returning a constant. A health
    check that never touches the database reports healthy while the database
    is unreachable, which keeps a broken instance in a load balancer's
    rotation.
    """
    database_ok = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "service": "civiclens-api",
        "database": "reachable" if database_ok else "unreachable",
    }