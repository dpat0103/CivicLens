"""
Build (or rebuild) the assistant's retrieval index.

Run after any data refresh:  python -m ingestion.build_index

Deliberately separate from application startup. Indexing is an occasional
batch job tied to the data refresh cadence, not something that should run on
every cold start of a free-tier web instance.
"""
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, SessionLocal
from app.rag.corpus import build_corpus
from app.rag.embeddings import get_embedder
from app.rag.store import index_corpus, corpus_stats

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



def main():
    print(f"Target: {_describe_target()}")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        embedder = get_embedder()
        chunks = build_corpus(db)
        if not chunks:
            print("No data found. Seed or ingest metrics first.")
            return
        count = index_corpus(db, chunks, embedder)
        print(f"Indexed {count} chunks using {type(embedder).__name__}.")
        print(corpus_stats(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
