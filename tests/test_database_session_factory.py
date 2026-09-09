import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch


from journalbot.database import create_session_factory

class TestCreateSessionFactory:
    def test_sqlite_memory_initializes_schema_and_returns_session_factory(self):
        factory = create_session_factory(":memory:")

        session = factory()
        try:
            # The factory is actually usable.
            assert session.bind is not None
            assert session.expire_on_commit is False

            # The migration column was added.
            columns = {
                row[1]
                for row in session.execute(
                    __import__("sqlalchemy").text(
                        "PRAGMA table_info(server_contexts)"
                    )
                )
            }
            assert "current_session_id" in columns
        finally:
            session.close()

    def test_sqlite_file_creates_parent_directory_and_database(
        self, tmp_path: Path
    ):
        database_path = tmp_path / "nested" / "db" / "test.sqlite"

        factory = create_session_factory(database_path)

        assert database_path.parent.is_dir()
        assert database_path.exists()

        session = factory()
        try:
            assert session.bind is not None
            assert session.expire_on_commit is False
        finally:
            session.close()

    def test_sqlite_does_not_run_migration_when_column_already_exists(
        self, tmp_path: Path
    ):
        database_path = tmp_path / "test.sqlite"

        # First invocation creates the schema and migration column.
        create_session_factory(database_path)

        # Second invocation exercises the "column already exists" branch.
        factory = create_session_factory(database_path)

        session = factory()
        try:
            columns = {
                row[1]
                for row in session.execute(
                    __import__("sqlalchemy").text(
                        "PRAGMA table_info(server_contexts)"
                    )
                )
            }
            assert "current_session_id" in columns
        finally:
            session.close()

    def test_sqlite_enables_foreign_keys(self):
        factory = create_session_factory(":memory:")

        session = factory()
        try:
            result = session.execute(
                __import__("sqlalchemy").text("PRAGMA foreign_keys")
            ).scalar_one()

            assert result == 1
        finally:
            session.close()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
    @patch("journalbot.database.create_engine")
    def test_postgres_creates_engine_with_expected_options(
        self, mock_create_engine
    ):
        engine = MagicMock()
        mock_create_engine.return_value = engine

        connection = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection

        result = MagicMock()
        result.fetchone.return_value = (("current_session_id",),)
        connection.exec_driver_sql.return_value = result

        factory = create_session_factory("postgresql://example")

        mock_create_engine.assert_called_once_with(
            "postgresql://example",
            future=True,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )

        connection.exec_driver_sql.assert_called_once_with(
            """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'server_contexts' AND column_name = 'current_session_id'
            """
        )

        assert factory.kw["bind"] is engine
        assert factory.kw["expire_on_commit"] is False

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
    @patch("journalbot.database.create_engine")
    def test_postgres_adds_missing_column(self, mock_create_engine):
        engine = MagicMock()
        mock_create_engine.return_value = engine

        connection = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection

        result = MagicMock()
        result.fetchone.return_value = None

        connection.exec_driver_sql.side_effect = [
            result,
            MagicMock(),
        ]

        factory = create_session_factory("postgresql://example")

        assert factory.kw["bind"] is engine
        assert factory.kw["expire_on_commit"] is False

        assert connection.exec_driver_sql.call_args_list == [
            call(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'server_contexts' AND column_name = 'current_session_id'
            """
            ),
            call(
                """
                    ALTER TABLE server_contexts 
                    ADD COLUMN current_session_id INTEGER REFERENCES sessions(id)
                """
            ),
        ]

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
    @patch("journalbot.database.create_engine")
    def test_database_url_environment_switches_to_postgres_branch(
            self, mock_create_engine
    ):
        engine = MagicMock()
        mock_create_engine.return_value = engine

        connection = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection

        result = MagicMock()
        result.fetchone.return_value = (("current_session_id",),)
        connection.exec_driver_sql.return_value = result

        create_session_factory("postgresql://example")

        mock_create_engine.assert_called_once_with(
            "postgresql://example",
            future=True,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
