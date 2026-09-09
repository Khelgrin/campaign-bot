from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy.orm import sessionmaker

from journalbot.database import create_session_factory


def test_postgres_adds_missing_current_session_id_column(monkeypatch):
    engine = MagicMock()
    connection = MagicMock()
    result = MagicMock()

    result.fetchone.return_value = None

    engine.begin.return_value.__enter__.return_value = connection
    connection.exec_driver_sql.return_value = result

    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr("journalbot.database.create_engine", create_engine)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

    factory = create_session_factory("postgresql://localhost/test")

    create_engine.assert_called_once_with(
        "postgresql://localhost/test",
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

    assert isinstance(factory, sessionmaker)

    assert connection.exec_driver_sql.call_count == 2

    alter_sql = connection.exec_driver_sql.call_args_list[1].args[0]

    assert "ALTER TABLE server_contexts" in alter_sql
    assert "ADD COLUMN current_session_id INTEGER" in alter_sql
    assert "REFERENCES sessions(id)" in alter_sql


def test_postgres_does_not_add_existing_current_session_id_column(monkeypatch):
    engine = MagicMock()
    connection = MagicMock()
    result = MagicMock()

    result.fetchone.return_value = ("current_session_id",)

    engine.begin.return_value.__enter__.return_value = connection
    connection.exec_driver_sql.return_value = result

    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr("journalbot.database.create_engine", create_engine)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

    factory = create_session_factory("postgresql://localhost/test")

    create_engine.assert_called_once_with(
        "postgresql://localhost/test",
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

    assert isinstance(factory, sessionmaker)

    connection.exec_driver_sql.assert_called_once()


def test_sqlite_file_database(monkeypatch, tmp_path):
    engine = MagicMock()
    connection = MagicMock()

    engine.begin.return_value.__enter__.return_value = connection

    # current_session_id does not exist.
    connection.exec_driver_sql.return_value = [
        (0, "id", "INTEGER"),
        (1, "name", "TEXT"),
    ]

    create_engine = MagicMock(return_value=engine)
    create_all = MagicMock()

    monkeypatch.setattr("journalbot.database.create_engine", create_engine)
    monkeypatch.setattr("journalbot.database.Base.metadata.create_all", create_all)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    database_path = tmp_path / "nested" / "journalbot.db"

    factory = create_session_factory(database_path)

    expected_url = f"sqlite:///{database_path.resolve().as_posix()}"

    create_engine.assert_called_once_with(
        expected_url,
        future=True,
    )

    create_all.assert_called_once_with(engine)

    assert database_path.parent.is_dir()
    assert isinstance(factory, sessionmaker)

    assert connection.exec_driver_sql.call_count == 2

    alter_sql = connection.exec_driver_sql.call_args_list[1].args[0]

    assert "ALTER TABLE server_contexts" in alter_sql
    assert "ADD COLUMN current_session_id INTEGER" in alter_sql
    assert "REFERENCES sessions(id)" in alter_sql


def test_sqlite_memory_database(monkeypatch):
    engine = MagicMock()
    connection = MagicMock()

    engine.begin.return_value.__enter__.return_value = connection

    # current_session_id does not exist.
    connection.exec_driver_sql.return_value = []

    create_engine = MagicMock(return_value=engine)
    create_all = MagicMock()

    monkeypatch.setattr("journalbot.database.create_engine", create_engine)
    monkeypatch.setattr("journalbot.database.Base.metadata.create_all", create_all)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    factory = create_session_factory(":memory:")

    create_engine.assert_called_once_with(
        "sqlite:///:memory:",
        future=True,
    )

    create_all.assert_called_once_with(engine)

    assert isinstance(factory, sessionmaker)

    assert connection.exec_driver_sql.call_count == 2

    alter_sql = connection.exec_driver_sql.call_args_list[1].args[0]

    assert "ALTER TABLE server_contexts" in alter_sql
    assert "ADD COLUMN current_session_id INTEGER" in alter_sql
    assert "REFERENCES sessions(id)" in alter_sql


def test_sqlite_does_not_add_existing_current_session_id_column(monkeypatch):
    engine = MagicMock()
    connection = MagicMock()

    engine.begin.return_value.__enter__.return_value = connection

    connection.exec_driver_sql.return_value = [
        (0, "id", "INTEGER"),
        (1, "current_session_id", "INTEGER"),
    ]

    create_engine = MagicMock(return_value=engine)
    create_all = MagicMock()

    monkeypatch.setattr("journalbot.database.create_engine", create_engine)
    monkeypatch.setattr("journalbot.database.Base.metadata.create_all", create_all)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    factory = create_session_factory(":memory:")

    create_engine.assert_called_once_with(
        "sqlite:///:memory:",
        future=True,
    )

    create_all.assert_called_once_with(engine)

    assert isinstance(factory, sessionmaker)

    # Only PRAGMA table_info() should execute.
    connection.exec_driver_sql.assert_called_once_with(
        "PRAGMA table_info(server_contexts)"
    )


def test_sqlite_accepts_string_path(monkeypatch, tmp_path):
    engine = MagicMock()
    connection = MagicMock()

    engine.begin.return_value.__enter__.return_value = connection

    connection.exec_driver_sql.return_value = [
        (0, "id", "INTEGER"),
        (1, "current_session_id", "INTEGER"),
    ]

    create_engine = MagicMock(return_value=engine)
    create_all = MagicMock()

    monkeypatch.setattr("journalbot.database.create_engine", create_engine)
    monkeypatch.setattr("journalbot.database.Base.metadata.create_all", create_all)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    database_path = str(tmp_path / "journalbot.db")

    factory = create_session_factory(database_path)

    expected_url = f"sqlite:///{Path(database_path).resolve().as_posix()}"

    create_engine.assert_called_once_with(
        expected_url,
        future=True,
    )

    assert isinstance(factory, sessionmaker)
