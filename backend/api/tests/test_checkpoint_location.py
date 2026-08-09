"""Where a paused run waits, and whether that place survives a deploy.

`api/checkpointing.py` exists to make one promise: a guided deep run stopped
for steering, or an agent turn stopped for tool approval, is still there after
the server is replaced. It keeps that promise by writing to SQLite instead of a
dict — and then hands the *location* to a default that can only be computed
when the application database is itself a file.

Against Postgres there is nothing to compute from, and the fallback is a path
relative to the working directory. In the image that is `/app`: the read-only
half of the container, wiped by every replacement, while the volume is at
`/data`. So the hosted configuration — the only one that has never been run —
persisted its paused runs into the thing a deploy throws away, and nothing
said so, because a file was genuinely written and genuinely read back for as
long as the container lived.

These pin the location rather than the mechanism. The mechanism already has
tests; the mechanism was never what was broken.
"""
from pathlib import Path

import pytest

from api import checkpointing
from api.config import settings

DOCKERFILE = Path(__file__).resolve().parents[3] / "Dockerfile"


def _env(dockerfile: str, key: str) -> str | None:
    """The last `ENV KEY=value` for `key`, which is the one that survives."""
    found = None
    for line in dockerfile.splitlines():
        line = line.strip()
        if line.startswith(f"ENV {key}="):
            found = line.split("=", 1)[1].strip()
    return found


@pytest.mark.skipif(not DOCKERFILE.exists(), reason="running outside the repo")
def test_the_image_keeps_paused_runs_on_the_volume():
    """The actual fix, and the only test that would have caught the bug.

    A unit test of the derivation could not: the derivation was correct for
    the database it was written for. What was wrong was that the image relied
    on it in a configuration where it does not apply.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")

    checkpoint = _env(text, "CHECKPOINT_PATH")
    assert checkpoint, "the image must state where paused runs live, not derive it"

    # /data is the volume in both compose files. Anywhere else in the image is
    # discarded when the container is replaced, which is every deploy.
    assert checkpoint.startswith("/data/"), checkpoint

    # The two other pieces of state that outlive a container, checked together
    # so the rule reads as one rule: persistent things live on the volume.
    assert (_env(text, "JWT_SECRET_FILE") or "").startswith("/data/")
    assert "/data/" in (_env(text, "DATABASE_URL") or "")


def test_checkpoints_sit_beside_a_file_database(monkeypatch):
    """The zero-infra install, where the default is right: one volume holds
    the database and the runs that are mid-flight against it."""
    monkeypatch.setattr(settings, "checkpoint_path", "")
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:////data/helix.db")

    resolved = Path(checkpointing._sqlite_path())
    assert resolved.name == "helix-checkpoints.db"
    assert resolved.parent == Path("/data")


def test_a_remote_database_has_nowhere_to_derive_from(monkeypatch):
    """Why the image states the path instead of trusting the default.

    This asserts the *hazard*, not a desired behaviour: with Postgres the
    fallback is relative, so whatever the working directory happens to be
    becomes the durability story. That is fine for a developer running from a
    checkout and wrong for a container, and it is why `CHECKPOINT_PATH` is set
    above — and why `connect()` warns when it sees this combination.
    """
    monkeypatch.setattr(settings, "checkpoint_path", "")
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://helix:helix@postgres:5432/helix"
    )

    assert not Path(checkpointing._sqlite_path()).is_absolute()


def test_an_explicit_path_wins(monkeypatch):
    """What the image relies on. If the setting were ever shadowed by the
    derivation, the fix above would be decoration."""
    monkeypatch.setattr(settings, "checkpoint_path", "/data/helix-checkpoints.db")
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://helix:helix@postgres:5432/helix"
    )

    assert checkpointing._sqlite_path() == "/data/helix-checkpoints.db"
