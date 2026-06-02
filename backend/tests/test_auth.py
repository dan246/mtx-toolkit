"""
Tests for the authentication layer:
  - User model password hashing
  - login / me / change-password endpoints
  - global auth guard on mutating endpoints
  - public-endpoint allowlist
"""

import pytest

from app import create_app, db
from app.models import User


@pytest.fixture(scope="module")
def auth_app():
    """A dedicated app instance with authentication ENABLED."""
    app = create_app("testing")
    app.config.update(
        {
            "TESTING": True,
            "AUTH_ENABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "JWT_SECRET_KEY": "test-secret",
            "BOOTSTRAP_ADMIN_USERNAME": "admin",
            "BOOTSTRAP_ADMIN_PASSWORD": "admin",
        }
    )
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            u = User(username="admin", role="admin", is_active=True)
            u.set_password("admin")
            db.session.add(u)
            db.session.commit()
    yield app


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


def _login(client, username="admin", password="admin"):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


class TestUserModel:
    def test_password_hashing_roundtrip(self, auth_app):
        with auth_app.app_context():
            u = User(username="alice")
            u.set_password("s3cret")
            assert u.password_hash != "s3cret"
            assert u.check_password("s3cret")
            assert not u.check_password("wrong")

    def test_to_dict_excludes_hash(self, auth_app):
        with auth_app.app_context():
            u = User(username="bob")
            u.set_password("x")
            assert "password_hash" not in u.to_dict()


class TestLogin:
    def test_login_success_returns_token(self, auth_client):
        resp = _login(auth_client)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["token"]
        assert data["user"]["username"] == "admin"

    def test_login_wrong_password(self, auth_client):
        resp = _login(auth_client, password="nope")
        assert resp.status_code == 401

    def test_login_missing_fields(self, auth_client):
        resp = auth_client.post("/api/auth/login", json={"username": "admin"})
        assert resp.status_code == 400


class TestAuthGuard:
    def test_protected_get_requires_token(self, auth_client):
        # /api/streams is not on the public allowlist
        resp = auth_client.get("/api/streams/")
        assert resp.status_code == 401

    def test_protected_request_with_token(self, auth_client):
        token = _login(auth_client).get_json()["token"]
        resp = auth_client.get(
            "/api/streams/", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_invalid_token_rejected(self, auth_client):
        resp = auth_client.get(
            "/api/streams/", headers={"Authorization": "Bearer garbage"}
        )
        assert resp.status_code == 401

    def test_public_health_endpoint_open(self, auth_client):
        resp = auth_client.get("/api/health/")
        assert resp.status_code == 200

    def test_public_playback_report_open(self, auth_client):
        # Submitted by unauthenticated browser players; must stay public.
        resp = auth_client.post("/api/health/playback-report", json={"stream_id": 1})
        assert resp.status_code != 401


class TestMeAndChangePassword:
    def test_me_returns_current_user(self, auth_client):
        token = _login(auth_client).get_json()["token"]
        resp = auth_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.get_json()["user"]["username"] == "admin"

    def test_change_password_flow(self, auth_app):
        client = auth_app.test_client()
        token = _login(client).get_json()["token"]
        # wrong current password
        bad = client.post(
            "/api/auth/change-password",
            json={"current_password": "wrong", "new_password": "newpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert bad.status_code == 400
        # too short
        short = client.post(
            "/api/auth/change-password",
            json={"current_password": "admin", "new_password": "abc"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert short.status_code == 400
        # success
        ok = client.post(
            "/api/auth/change-password",
            json={"current_password": "admin", "new_password": "newpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok.status_code == 200
        # old password no longer works
        assert _login(client, password="admin").status_code == 401
        assert _login(client, password="newpass123").status_code == 200
