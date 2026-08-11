"""
Database connection setup.

Defaults to a local SQLite file so the project runs with zero external
services. Set DATABASE_URL in a .env file to point at Postgres instead
(e.g. postgresql://user:pass@localhost:5432/civiclens) -- no code changes
needed, SQLAlchemy handles both.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./civiclens.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
