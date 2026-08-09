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
from pathlib import Path

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

# backend/, two levels up from api/tests/. Derived from the path rather than
# split on a literal "/api/": on Windows `__file__` uses backslashes, the split
# found nothing, and BACKEND became the path of this file — so every test here
# failed with "Path doesn't exist: ...test_migrations.py/migrations". Four of
# the six failures a developer on Windows learned to expect were this line,
# which also meant the drift guard — the thing that catches a model change
# without a migration — never actually ran outside CI.
BACKEND = Path(__file__).resolve().parents[2]


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
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


# --- the blind spot in every check above -------------------------------------
# All of them run on SQLite, which stores timestamps as text and renders both
# `DateTime()` and `DateTime(timezone=True)` as TIMESTAMP. So they compare
# equal, `compare_type` sees nothing, and a naive column reaches Postgres —
# where asyncpg refuses to write the tz-aware values this product produces, and
# the write 500s.
#
# That has now happened twice: e7b3c95a1d84 repaired thirteen such columns, and
# b6f30d7a4e51 added a fourteenth one table later. The two below are the only
# checks here that do not need a Postgres server to notice it.


def test_every_timestamp_column_carries_its_timezone():
    """The models. `api/db.py` maps `Mapped[datetime]` to a tz-aware column, so
    this passes by construction — until someone spells a column out by hand and
    leaves the flag off, which is how the original thirteen happened."""
    naive = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, sa.DateTime) and not column.type.timezone
    ]
    assert naive == [], f"naive timestamp columns: {naive}"


def test_no_migration_after_the_repair_creates_a_naive_timestamp():
    """The migrations, which the check above cannot reach: they are source, not
    metadata, and they are the path a hosted deploy actually takes.

    Read as text on purpose. Executing them proves nothing here — the proof
    would have to run on Postgres, and the whole point is to fail on a laptop
    that only has SQLite.

    Scoped to what comes *after* e7b3c95a1d84, walking the real revision chain
    rather than trusting filenames. Naive columns before it are history: the
    baseline declared thirteen and the repair is what corrects them. A naive
    column after it is a regression, which is the only thing worth failing on.
    """
    cfg = _alembic_config("sqlite://")
    # walk_revisions runs head -> base, so reversing gives application order.
    chain = list(reversed(list(ScriptDirectory.from_config(cfg).walk_revisions())))
    cut = next(
        (i for i, rev in enumerate(chain) if rev.revision == "e7b3c95a1d84"), None
    )
    assert cut is not None, "the tz repair is missing from the revision chain"

    offenders = []
    for rev in chain[cut + 1 :]:
        path = Path(rev.path)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "DateTime()" in line.split("#", 1)[0]:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")

    assert offenders == [], (
        "Timestamp columns must be sa.DateTime(timezone=True) — Postgres "
        "rejects an aware value into a naive column, and SQLite will not tell "
        "you.\n" + "\n".join(offenders)
    )


def test_downgrade_is_reversible(tmp_path):
    """A baseline that cannot be undone is a baseline nobody dares apply."""
    async_url, sync_url = _db_urls(tmp_path)
    cfg = _alembic_config(async_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    insp = sa.inspect(sa.create_engine(sync_url))
    remaining = [t for t in insp.get_table_names() if t != "alembic_version"]
    assert remaining == []
