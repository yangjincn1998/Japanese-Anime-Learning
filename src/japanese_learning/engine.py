from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session, sessionmaker


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection: object, _: object) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA busy_timeout = 10000")
    cursor.close()


def database_url(path: str | Path) -> URL:
    return URL.create("sqlite+pysqlite", database=str(Path(path).resolve()))


def create_database_engine(
    path: str | Path,
    *,
    must_exist: bool = False,
) -> Engine:
    db_path = Path(path).resolve()
    if must_exist and not db_path.is_file():
        raise FileNotFoundError(db_path)
    return create_engine(database_url(db_path), future=True)


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent / "migrations"),
    )
    return config


def upgrade_database(engine: Engine) -> None:
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def initialize_database(
    path: str | Path,
    *,
    replace: bool = False,
) -> Engine:
    db_path = Path(path).resolve()
    if replace:
        db_path.unlink(missing_ok=True)
        db_path.with_name(db_path.name + "-wal").unlink(missing_ok=True)
        db_path.with_name(db_path.name + "-shm").unlink(missing_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(db_path)
    try:
        upgrade_database(engine)
    except Exception:
        engine.dispose()
        raise
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
