from datetime import datetime, timedelta, timezone

import pytest

from server.extensions import db
from server.models import User
from tests.test_tenants import client, world  # noqa: F401


@pytest.mark.parametrize(
    "password",
    [
        "shortA!1",
        "ShortA!12",
        "alllowercase123!",
        "ALLUPPERCASE123!",
        "NoNumberPassword!",
        "NoSymbolPassword123",
    ],
)
def test_registration_rejects_weak_passwords(client, password):
    response = client.post(
        "/api/auth/register",
        json={"name": "Test", "email": "test@example.com", "password": password},
    )

    assert response.status_code == 400
    assert response.get_json()["error"].startswith("Password")


def test_registration_accepts_strong_password(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Test",
            "email": "test@example.com",
            "password": "Abcde!1234",
        },
    )

    assert response.status_code == 201
    assert "password_hash" not in response.get_json()["user"]


def test_refresh_rotates_and_revokes_the_previous_refresh_token(client, world):
    login_response = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    refresh_token = login_response.get_json()["refresh_token"]

    refreshed = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert refreshed.status_code == 200
    assert refreshed.get_json()["refresh_token"] != refresh_token
    assert client.get(
        "/api/auth/me",
        headers={
            "Authorization": f"Bearer {refreshed.get_json()['access_token']}"
        },
    ).status_code == 200

    reused = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert reused.status_code == 401


def test_logout_revokes_refresh_token(client, world):
    login_response = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    refresh_token = login_response.get_json()["refresh_token"]

    logout = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert logout.status_code == 200
    assert client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    ).status_code == 401


def test_login_temporarily_locks_after_repeated_failures(client, world):
    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={"email": "lana@x.com", "password": "WrongPassword!1"},
        )
        assert response.status_code == 401

    locked = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    assert locked.status_code == 401
    assert locked.get_json()["error"] == "Invalid email or password"

    user = db.session.get(User, world["ids"]["landlord"])
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None


def test_login_lockout_expires_and_success_resets_attempts(client, world):
    user = db.session.get(User, world["ids"]["landlord"])
    user.failed_login_attempts = 5
    user.login_attempt_window_started_at = datetime.now(timezone.utc)
    user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )

    assert response.status_code == 200
    user = db.session.get(User, world["ids"]["landlord"])
    assert user.failed_login_attempts == 0
    assert user.login_attempt_window_started_at is None
    assert user.locked_until is None
