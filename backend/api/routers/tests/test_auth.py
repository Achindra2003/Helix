"""Account hygiene: change password, delete account."""
from starlette.testclient import TestClient

from api.main import app


def test_change_password_requires_correct_current_password(make_user):
    with TestClient(app) as client:
        headers, _uid = make_user(client, email="pw@test.dev")

        wrong = client.patch(
            "/api/me/password",
            json={"current_password": "nope", "new_password": "newpass123"},
            headers=headers,
        )
        assert wrong.status_code == 401

        ok = client.patch(
            "/api/me/password",
            json={"current_password": "pw123456", "new_password": "newpass123"},
            headers=headers,
        )
        assert ok.status_code == 204

        # Old password no longer works; the new one does.
        relogin_old = client.post(
            "/api/auth/login", json={"email": "pw@test.dev", "password": "pw123456"}
        )
        assert relogin_old.status_code == 401
        relogin_new = client.post(
            "/api/auth/login", json={"email": "pw@test.dev", "password": "newpass123"}
        )
        assert relogin_new.status_code == 200


def test_delete_account_blocked_while_owning_a_workspace(make_workspace):
    with TestClient(app) as client:
        headers, _uid, _wid = make_workspace(client)

        blocked = client.delete("/api/me", headers=headers)
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "owns_workspaces"


def test_delete_account_succeeds_for_a_plain_member(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _oid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, owner_headers, wid)

        deleted = client.delete("/api/me", headers=member_headers)
        assert deleted.status_code == 204

        # The token is now for a nonexistent user.
        after = client.get("/api/me", headers=member_headers)
        assert after.status_code == 401
