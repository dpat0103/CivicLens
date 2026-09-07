"""
Add Metric.provenance to an existing database.

Needed because SQLAlchemy's create_all() creates missing tables but never
alters existing ones, so a database created before this column existed will
fail on every query with "no such column: metrics.provenance".

Safe to run repeatedly. Works against both the local SQLite file and Neon.

    python -m ingestion.migrate_provenance
    python -m ingestion.migrate_provenance --mark-simulated

--mark-simulated stamps every existing row as simulated. Use it when the
database was populated by seed_data.py, since those values are generated
rather than measured and are otherwise attributed to the Census and BLS.
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app.database import engine

def _describe_target() -> str:
    """Print which database is being written to. DATABASE_URL in backend/.env
    silently redirects local commands at Neon, and writing an index to
    production while you think you are working locally is an easy mistake to
    make only once."""
    from sqlalchemy.engine import make_url
    url = make_url(str(engine.url))
    if url.drivername.startswith("sqlite"):
        return f"local SQLite file ({url.database})"
    return f"{url.drivername} at {url.host}/{url.database}"



def column_exists() -> bool:
    return "provenance" in {c["name"] for c in inspect(engine).get_columns("metrics")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark-simulated", action="store_true",
                        help="stamp all existing rows as simulated demo data")
    args = parser.parse_args()

    print(f"Target: {_describe_target()}")

    if "metrics" not in inspect(engine).get_table_names():
        print("No metrics table found. Run the seed or ingestion job first.")
        return

    dialect = engine.dialect.name

    with engine.begin() as conn:
        if column_exists():
            print("Column 'provenance' already present, skipping ALTER.")
        else:
            # SQLite cannot add a NOT NULL column without a default, and its
            # ALTER support is limited, so both dialects get the same
            # default-backed form.
            conn.execute(text(
                "ALTER TABLE metrics ADD COLUMN provenance VARCHAR(12) "
                "NOT NULL DEFAULT 'measured'"
            ))
            print(f"Added metrics.provenance ({dialect}).")

        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_metrics_provenance "
                "ON metrics (provenance)"
            ))
        except Exception as exc:  # index is an optimisation, not a requirement
            print(f"Index creation skipped: {exc}")

        if args.mark_simulated:
            result = conn.execute(text("UPDATE metrics SET provenance = 'simulated'"))
            print(f"Marked {result.rowcount} rows as simulated.")

        rows = conn.execute(text(
            "SELECT provenance, COUNT(*) FROM metrics GROUP BY provenance"
        )).all()
        print("Current provenance breakdown:", dict(rows))


if __name__ == "__main__":
    main()
