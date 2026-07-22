from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


@lru_cache
def get_engine() -> Engine:
    """Create and cache the database engine when it is first required."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Create and cache the database session factory when first required."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def create_db_session() -> Session:
    """Create a database session using the lazily initialised factory."""
    return get_session_factory()()


def get_db_session() -> Generator[Session, None, None]:
    session = create_db_session()

    try:
        yield session
    finally:
        session.close()
