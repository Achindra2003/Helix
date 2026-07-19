"""Alembic baseline (P3).

The point of these is drift. Self-hosters get `create_all` at boot and the
hosted instance gets `alembic upgrade head`; if those two ever build different
schemas, the difference shows up as a confusing runtime error on one population
only, long after the change that caused it. So: assert they agree, and assert
that a model change without a matching migration fails here rather than in
production.

These drive Alembic through its Python API against a throwaway SQLite file
rather than shelling out, so they work the same in CI as locally.
"""
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from api.db import Base

# Importing every model module is what puts the tables on Base.metadata. If one
# is missing, metadata is short a table and the comparison below is meaningless
# — so this list is the test's real fixture, not boilerplate.
from api import models, telemetry  # noqa: F401
from api.conversation import embeddings, models as conversation_models  # noqa: F401
from api.documents import models as document_models  # noqa: F401
from api.prompts import models as prompt_models  # noqa: F401

BACKEND = __file__.rsplit("/api/", 1)[0]


def _alembic_config(db_url: str) -> Config:
    cfg = Config(f"{BACKEND}/alembic.ini")
    cfg.set_main_option("script_location", f"{BACKEND}/migrations")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _db_urls(tmp_path, name="migrated"):
    """(async, sync) URLs for the same file.

    env.py builds an async engine, so Alembic must be handed the aiosqlite
    driver; the inspector afterwards is synchronous and needs the plain one.
    Same file either way.
    """
    path = f"{tmp_path}/{name}.db"
    return f"sqlite+aiosqlite:///{path}", f"sqlite:///{path}"


def test_migrations_run_and_reach_head(tmp_path):
    async_url, sync_url = _db_urls(tmp_path)
    command.upgrade(_alembic_config(async_url), "head")

    engine = sa.create_engine(sync_url)
    with engine.connect() as conn:
        stamped = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    expected = ScriptDirectory.from_config(_alembic_config(async_url)).get_current_head()
    assert stamped == expected


def test_models_match_the_migrations(tmp_path):
    """The drift guard: change a model, add a migration, or this fails.

    `compare_metadata` is exactly what `--autogenerate` uses to decide what to
    write, so an empty diff means autogenerate would produce an empty migration
    — the definition of "the migrations are current".
    """
    async_url, sync_url = _db_urls(tmp_path)
    command.upgrade(_alembic_config(async_url), "head")

    engine = sa.create_engine(sync_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)

    assert diff == [], (
        "Models and migrations disagree. Run:\n"
        "  alembic revision --autogenerate -m 'describe the change'\n"
        f"Outstanding differences: {diff}"
    )


def test_migrated_schema_matches_create_all(tmp_path):
    """Both install paths must produce the same tables and columns.

    Compared as sets: SQLite emits table constraints in construction order, so
    two identical schemas can differ as DDL text.
    """
    migrated_async, migrated_sync = _db_urls(tmp_path)
    command.upgrade(_alembic_config(migrated_async), "head")

    _, created_sync = _db_urls(tmp_path, "created")
    created_engine = sa.create_engine(created_sync)
    Base.metadata.create_all(created_engine)

    def snapshot(engine):
        insp = sa.inspect(engine)
        return {
            table: {
                (c["name"], str(c["type"]), bool(c["nullable"]))
                for c in insp.get_columns(table)
            }
            for table in insp.get_table_names()
            if table != "alembic_version"
        }

    migrated = snapshot(sa.create_engine(migrated_sync))
    created = snapshot(created_engine)

    assert set(migrated) == set(created)
    for table in sorted(migrated):
        assert migrated[table] == created[table], f"{table} differs"


def test_downgrade_is_reversible(tmp_path):
    """A baseline that cannot be undone is a baseline nobody dares apply."""
    async_url, sync_url = _db_urls(tmp_path)
    cfg = _alembic_config(async_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    insp = sa.inspect(sa.create_engine(sync_url))
    remaining = [t for t in insp.get_table_names() if t != "alembic_version"]
    assert remaining == []
