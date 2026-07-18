"""The boot-time secret guard (P2).

An instance running on the placeholder signing secret can have a session
forged for any user by anyone who has read this repository, so the app must
not start that way. These tests pin the three outcomes: refuse, generate and
persist, or accept what was configured.
"""
import pytest

from api.config import (
    PLACEHOLDER_JWT_SECRET,
    InsecureConfigError,
    Settings,
    secure_jwt_secret,
)


def _cfg(**overrides) -> Settings:
    """Settings built from explicit values only.

    `_env_file=None` matters: without it pydantic-settings reads the
    developer's real backend/.env, and a machine that happens to have a proper
    JWT_SECRET there would pass these tests for the wrong reason.
    """
    return Settings(_env_file=None, **overrides)


def test_refuses_to_boot_on_the_placeholder():
    with pytest.raises(InsecureConfigError) as exc:
        secure_jwt_secret(_cfg(jwt_secret=PLACEHOLDER_JWT_SECRET))
    assert "Refusing to start" in str(exc.value)


def test_error_message_carries_a_usable_replacement():
    """The fix must be copy-pasteable, or self-hosters will look for a way to
    disable the check instead of setting a secret."""
    with pytest.raises(InsecureConfigError) as exc:
        secure_jwt_secret(_cfg(jwt_secret=PLACEHOLDER_JWT_SECRET))
    message = str(exc.value)
    assert "JWT_SECRET=" in message
    suggested = message.split("JWT_SECRET=")[1].split("\n")[0].strip()
    assert len(suggested) >= 32
    assert suggested != PLACEHOLDER_JWT_SECRET


def test_configured_secret_is_used_unchanged():
    assert secure_jwt_secret(_cfg(jwt_secret="a-real-secret")) == "a-real-secret"


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_secret_is_treated_as_unset_not_as_a_secret(blank):
    """`JWT_SECRET: ${JWT_SECRET:-}` in compose yields an empty string when the
    operator set nothing. Signing tokens with "" would be worse than the
    placeholder, so blank must take the refuse/generate path."""
    with pytest.raises(InsecureConfigError):
        secure_jwt_secret(_cfg(jwt_secret=blank))


def test_blank_secret_still_generates_when_a_file_is_configured(tmp_path):
    target = tmp_path / ".jwt_secret"
    generated = secure_jwt_secret(_cfg(jwt_secret="", jwt_secret_file=str(target)))
    assert len(generated) >= 32
    assert target.read_text().strip() == generated


def test_helix_dev_opts_out():
    """Local development keeps working without ceremony."""
    cfg = _cfg(jwt_secret=PLACEHOLDER_JWT_SECRET, helix_dev=True)
    assert secure_jwt_secret(cfg) == PLACEHOLDER_JWT_SECRET


def test_generates_and_persists_when_a_secret_file_is_configured(tmp_path):
    """The container path: no JWT_SECRET, but a writable file location."""
    target = tmp_path / "sub" / ".jwt_secret"
    cfg = _cfg(jwt_secret=PLACEHOLDER_JWT_SECRET, jwt_secret_file=str(target))

    generated = secure_jwt_secret(cfg)

    assert generated != PLACEHOLDER_JWT_SECRET
    assert len(generated) >= 32
    assert target.read_text().strip() == generated
    # Not world- or group-readable: 0600.
    assert target.stat().st_mode & 0o077 == 0


def test_persisted_secret_is_reused_across_restarts(tmp_path):
    """Regenerating per boot would log the whole team out on every restart."""
    target = tmp_path / ".jwt_secret"
    cfg = _cfg(jwt_secret=PLACEHOLDER_JWT_SECRET, jwt_secret_file=str(target))

    first = secure_jwt_secret(cfg)
    second = secure_jwt_secret(cfg)

    assert first == second


def test_explicit_secret_beats_the_secret_file(tmp_path):
    """An operator who sets JWT_SECRET means it; a stale file must not win."""
    target = tmp_path / ".jwt_secret"
    target.write_text("secret-from-file")
    cfg = _cfg(jwt_secret="secret-from-env", jwt_secret_file=str(target))

    assert secure_jwt_secret(cfg) == "secret-from-env"


def test_unwritable_secret_file_fails_loudly(tmp_path):
    """Silently falling back to the placeholder here would defeat the guard."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file")
    cfg = _cfg(
        jwt_secret=PLACEHOLDER_JWT_SECRET,
        jwt_secret_file=str(blocker / "nested" / ".jwt_secret"),
    )

    with pytest.raises(InsecureConfigError):
        secure_jwt_secret(cfg)
