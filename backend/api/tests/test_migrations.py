"""Alembic baseline (P3).

The point of these is drift. Self-hosters get `create_all` at boot and the
hosted instance gets `alembic upgrade head`; if those two ever build different
schemas, the difference shows up as a confusing runtime error on one population
only, long after the change that caused it. So: assert they agree, and assert
that a model change without a matching migration fails here rather than in
production.

These drive Alembic through its Python API rather than shelling out, against a
throwaway SQLite file by default — so they work the same in CI as locally, on a
laptop with no database server.

Set `MIGRATION_TEST_DATABASE_URL` and the identical checks run against a real
Postgres, each on its own freshly created database. CI does that. Both matter:
SQLite is what makes them cheap enough to run on every change, and Postgres is
the only dialect that can see a whole class of defect the others cannot — see
the note above `test_every_timestamp_column_carries_its_timezone`.
"""
import os
import re
from pathlib import Path

import pytest
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


# Set to a Postgres URL and every check in this file runs there instead of on a
# throwaway SQLite file. CI does that (.github/workflows/ci.yml, job
# `backend-postgres`), which is the only place it happens: the point is a
# dialect that can tell two spellings apart, and no laptop here has a server.
#
# This is the gap that made the naive-timestamp defect possible. The suite runs
# against Postgres in CI, but it builds its schema with `create_all` — so the
# *migrations* had still never touched a real server, and a migration is what a
# hosted deploy actually applies. That defect bit "on any instance whose schema
# came from Alembic rather than create_all", which is precisely the path
# nothing exercised.
_PG_BASE = os.environ.get("MIGRATION_TEST_DATABASE_URL", "")


def _db_urls(tmp_path, name="migrated"):
    """(async, sync) URLs for one throwaway database.

    env.py builds an async engine, so Alembic must be handed an async driver;
    the inspector afterwards is synchronous and needs the sync one. Same
    database either way — that is the whole contract, and the callers below do
    not care which server is behind it.
    """
    if not _PG_BASE:
        path = f"{tmp_path}/{name}.db"
        return f"sqlite+aiosqlite:///{path}", f"sqlite:///{path}"

    # A real server has no equivalent of "a file in tmp_path", so make one:
    # a fresh database per call, named after the test that asked. Dropped
    # first rather than after, so a crashed run leaves evidence and the next
    # run still starts clean. Postgres caps identifiers at 63 characters.
    db = re.sub(r"[^a-z0-9_]", "_", f"migtest_{name}_{tmp_path.name}".lower())[:60]
    url = sa.engine.make_url(_PG_BASE)
    admin = sa.create_engine(
        # "postgres" is the maintenance database: CREATE DATABASE cannot run
        # inside a transaction, and cannot run from the database it creates.
        url.set(drivername="postgresql+psycopg2", database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{db}"'))
    admin.dispose()

    # Left behind on purpose. In CI the whole server is a service container
    # thrown away with the job, and locally the drop above makes a rerun
    # idempotent — so cleanup would only buy tidiness, at the cost of a
    # teardown that runs while a failed test still wants its schema.
    # render_as_string(hide_password=False), not str(): SQLAlchemy's __str__
    # renders the password as "***", and these strings are handed to Alembic
    # and to create_engine as connection URLs. The masked form is a valid URL
    # with the wrong password, so it fails as an authentication error rather
    # than as anything that mentions masking.
    return (
        url.set(drivername="postgresql+asyncpg", database=db).render_as_string(
            hide_password=False
        ),
        url.set(drivername="postgresql+psycopg2", database=db).render_as_string(
            hide_password=False
        ),
    )


def test_the_server_is_actually_reached_when_one_is_configured(tmp_path):
    """That the Postgres mode is really in use, when CI says it should be.

    Everything else in this file passes on SQLite. So if the workflow's
    `MIGRATION_TEST_DATABASE_URL` were misspelled, or set on the wrong step, or
    dropped in a refactor, these checks would quietly go back to proving
    nothing about Postgres and still report green — which is exactly the shape
    of defect this file exists to catch, turned on the file itself.

    Skipped rather than failed without the variable: SQLite is the honest
    default for a laptop, and this only has an opinion about the case where
    somebody has claimed a server.
    """
    if not _PG_BASE:
        pytest.skip("no MIGRATION_TEST_DATABASE_URL — SQLite mode is the default")
    async_url, sync_url = _db_urls(tmp_path)
    assert async_url.startswith("postgresql+asyncpg://"), async_url
    assert sync_url.startswith("postgresql+psycopg2://"), sync_url


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
# On SQLite — which is how they run unless MIGRATION_TEST_DATABASE_URL is set —
# timestamps are text, and both `DateTime()` and `DateTime(timezone=True)`
# render as TIMESTAMP. So they compare equal, `compare_type` sees nothing, and
# a naive column reaches Postgres, where asyncpg refuses to write the tz-aware
# values this product produces and the write 500s.
#
# That has now happened twice: e7b3c95a1d84 repaired thirteen such columns, and
# b6f30d7a4e51 added a fourteenth one table later.
#
# Pointing the checks above at Postgres closes the hole properly, and CI now
# does. The two below stay regardless, because they are the ones that fail on a
# laptop — the machine where the mistake is actually made, minutes after it is
# made, rather than on a push. A guard that only fires in CI is a guard you
# argue with; one that fires locally is one you fix.


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
