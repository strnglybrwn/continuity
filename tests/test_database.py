import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.persistence import database


def test_database_module_import_does_not_require_password() -> None:
    project_root = Path(__file__).resolve().parents[1]

    environment = os.environ.copy()
    environment.pop("CONTINUITY_DATABASE_PASSWORD", None)
    environment.pop("CONTINUITY_DATABASE_PASSWORD_FILE", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.persistence.database",
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_get_engine_creates_engine_only_when_called(
    monkeypatch,
) -> None:
    fake_engine = Mock()
    mocked_create_engine = Mock(return_value=fake_engine)
    test_database_url = "postgresql+psycopg://user:password@database/test"

    database.get_engine.cache_clear()
    database.get_session_factory.cache_clear()

    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(database_url=test_database_url),
    )
    monkeypatch.setattr(
        database,
        "create_engine",
        mocked_create_engine,
    )

    assert mocked_create_engine.call_count == 0

    engine = database.get_engine()

    assert engine is fake_engine
    mocked_create_engine.assert_called_once_with(
        test_database_url,
        pool_pre_ping=True,
    )

    database.get_engine.cache_clear()
    database.get_session_factory.cache_clear()


def test_get_engine_is_cached(monkeypatch) -> None:
    fake_engine = Mock()
    mocked_create_engine = Mock(return_value=fake_engine)

    database.get_engine.cache_clear()
    database.get_session_factory.cache_clear()

    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(
            database_url=("postgresql+psycopg://user:password@database/test"),
        ),
    )
    monkeypatch.setattr(
        database,
        "create_engine",
        mocked_create_engine,
    )

    first_engine = database.get_engine()
    second_engine = database.get_engine()

    assert first_engine is fake_engine
    assert second_engine is fake_engine
    mocked_create_engine.assert_called_once()

    database.get_engine.cache_clear()
    database.get_session_factory.cache_clear()
