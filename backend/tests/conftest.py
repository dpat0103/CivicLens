"""Shared fixtures.

Everything runs offline: an in-memory SQLite database, the hashing embedder
and the extractive generator. The environment is pinned before any app
module is imported, because app.database reads DATABASE_URL at import time
and load_dotenv() would otherwise let a developer's .env point the suite at
a real database.
"""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMBEDDING_PROVIDER"] = "hashing"
os.environ["LLM_PROVIDER"] = "extractive"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.rag import store  # noqa: E402
from app.rag.corpus import build_corpus  # noqa: E402
from app.rag.embeddings import HashingEmbedder  # noqa: E402

from .fixture_data import populate  # noqa: E402


def _make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


@pytest.fixture(scope="session")
def db():
    """Fixture municipalities with measured data and a built retrieval index.

    Session-scoped because building the index is the slow part and no test
    writes to it. Tests that need different data use `empty_db`.
    """
    session = _make_session()
    populate(session)
    store.index_corpus(session, build_corpus(session), HashingEmbedder())
    yield session
    session.close()


@pytest.fixture
def empty_db():
    session = _make_session()
    yield session
    session.close()


@pytest.fixture
def location_by_name(db):
    def lookup(name: str) -> models.Location:
        return db.query(models.Location).filter(models.Location.name == name).one()

    return lookup
