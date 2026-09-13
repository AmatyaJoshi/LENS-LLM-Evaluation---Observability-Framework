"""Relational database session layer (Postgres in production, SQLite in tests).

Schema changes go through Alembic (``apps/api/migrations/alembic``). For SQLite
DSNs (tests, ``--lite`` dev) tables are created directly from the SQLModel
metadata because Alembic's Postgres-specific migration (pgvector) does not apply.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import lens_api.models.sql  # noqa: F401  (register tables)


def make_engine(dsn: str) -> Engine:
    if dsn.startswith("sqlite"):
        return create_engine(
            dsn,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool if ":memory:" in dsn or dsn == "sqlite://" else None,
        )
    return create_engine(dsn, pool_pre_ping=True)


def init_db(engine: Engine) -> None:
    """Create tables for SQLite; Postgres schemas are managed by Alembic."""
    if engine.dialect.name == "sqlite":
        SQLModel.metadata.create_all(engine)


@lru_cache(maxsize=4)
def _cached_engine(dsn: str) -> Engine:
    engine = make_engine(dsn)
    init_db(engine)
    return engine


def engine_for(dsn: str) -> Engine:
    """One engine per DSN; in-memory SQLite is never shared (each app gets a fresh database)."""
    if dsn.startswith("sqlite") and (":memory:" in dsn or dsn == "sqlite://"):
        engine = make_engine(dsn)
        init_db(engine)
        return engine
    return _cached_engine(dsn)


def get_session(request: Request) -> Iterator[Session]:
    engine: Engine = request.app.state.db_engine
    with Session(engine) as session:
        yield session
