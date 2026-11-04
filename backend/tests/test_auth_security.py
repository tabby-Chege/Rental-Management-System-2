from datetime import datetime, timedelta, timezone
import re

import pyotp
import pytest

from server.extensions import db
from server.models import User
from server.models_auth_factors import (
    AuthFactorChallenge,
    AuthOtpChallenge,
    PasskeyCredential,
    RecoveryCode,
)
from server.models_payment import EmailOutbox
from server.payment_service import (
    decrypt_mfa_email_body,
    process_email_outbox,
    queue_email,
)
from server.routes.auth import challenge_digest, code_digest, decrypt_totp_secret
from tests.test_tenants import client, world  # noqa: F401


@pytest.fixture(autouse=True)
def stub_auth_email_delivery(monkeypatch):
    from server.routes import auth

    monkeypatch.setattr(auth, "deliver_email_outbox_event", lambda _event_key: True)


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
    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Test",
            "email": "test@example.com",
            "password": "Abcde!1234",
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["flow"] == "registration"
    assert data["factor_step"] == "email_otp"
    assert data["challenge_token"]
    assert "password_hash" not in data["user"]
    assert "access_token" not in data
    assert "refresh_token" not in data


def test_existing_account_login_issues_jwt_for_authenticated_requests(client, world):
    response = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["user"]["role"] == "landlord"
    assert data["access_token"]
    assert data["refresh_token"]
    assert "password_hash" not in data["user"]

    authenticated = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert authenticated.status_code == 200
    assert authenticated.get_json()["user"]["email"] == "lana@x.com"


def test_newly_registered_account_verifies_email_and_enrolls_totp(
    client, monkeypatch
):
    from server.routes import auth

    codes = iter([0, 0, 1])

    def deterministic_randbelow(_upper):
        return next(codes, 0)

    monkeypatch.setattr(auth.secrets, "randbelow", deterministic_randbelow)
    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    registration = client.post(
        "/api/auth/register",
        json={
            "name": "New Tenant",
            "email": "new-tenant@example.com",
            "password": "Abcde!1234",
            "role": "tenant",
        },
    )
    assert registration.status_code == 201
    challenge = registration.get_json()
    assert challenge["factor_step"] == "email_otp"
    assert challenge["flow"] == "registration"
    assert "access_token" not in challenge
    assert "refresh_token" not in challenge

    cooldown = client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
        },
    )
    assert cooldown.status_code == 429

    registration_otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(challenge["challenge_token"]),
        method="email",
    ).one()
    registration_otp.created_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    db.session.commit()
    registration_code = email_code_for(challenge["challenge_token"])
    login = client.post(
        "/api/auth/login",
        json={"email": "new-tenant@example.com", "password": "Abcde!1234"},
    )
    login_challenge = login.get_json()
    assert login.status_code == 200
    assert login_challenge["factor_step"] == "email_otp"
    login_verification = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": login_challenge["challenge_token"],
            "method": "email",
            "code": registration_code,
        },
    )
    assert login_verification.status_code == 401
    assert "access_token" not in login_verification.get_json()

    enrollment = verify_email_factor(client, challenge)
    assert enrollment["factor_step"] == "authenticator_enrollment"
    assert enrollment["flow"] == "registration"
    assert "access_token" not in enrollment
    assert client.get("/api/payments").status_code == 401
    completed = complete_totp_enrollment(client, enrollment["challenge_token"])
    assert completed["user"]["role"] == "tenant"
    assert completed["access_token"]
    assert completed["refresh_token"]

    login_otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(login_challenge["challenge_token"]),
        method="email",
    ).one()
    login_otp.created_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    db.session.commit()
    login = client.post(
        "/api/auth/login",
        json={"email": "new-tenant@example.com", "password": "Abcde!1234"},
    )
    assert login.status_code == 200
    assert login.get_json()["factor_step"] == "email_otp"
    assert "flow" not in login.get_json()


def test_incomplete_registration_can_resume_with_a_fresh_login_challenge(
    client, monkeypatch
):
    from server.routes import auth

    codes = iter([0, 0, 1])

    def deterministic_randbelow(_upper):
        return next(codes, 0)

    monkeypatch.setattr(auth.secrets, "randbelow", deterministic_randbelow)
    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    registration = client.post(
        "/api/auth/register",
        json={
            "name": "Resuming Tenant",
            "email": "resuming@example.com",
            "password": "Abcde!1234",
            "role": "tenant",
        },
    )
    assert registration.status_code == 201
    registration_challenge = registration.get_json()

    registration_otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(registration_challenge["challenge_token"]),
        method="email",
    ).one()
    registration_otp.created_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    db.session.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": "resuming@example.com", "password": "Abcde!1234"},
    )
    login_challenge = login.get_json()
    assert login.status_code == 200
    assert login_challenge["factor_step"] == "email_otp"
    assert login_challenge.get("flow") is None
    assert login_challenge["challenge_token"] != registration_challenge["challenge_token"]

    registration_code = email_code_for(registration_challenge["challenge_token"])
    wrong_purpose = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": login_challenge["challenge_token"],
            "method": "email",
            "code": registration_code,
        },
    )
    assert wrong_purpose.status_code == 401
    assert "access_token" not in wrong_purpose.get_json()

    enrollment = verify_email_factor(client, login_challenge)
    assert enrollment["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in enrollment
    completed = complete_totp_enrollment(client, enrollment["challenge_token"])
    assert completed["access_token"]


def test_wrong_password_and_unknown_email_have_the_same_safe_error(client, world):
    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "WrongPassword!1"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "WrongPassword!1"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.get_json()["error"] == "Invalid email or password"
    assert unknown_email.get_json()["error"] == "Invalid email or password"


def test_locked_account_rejects_correct_password(client, world):
    user = db.session.get(User, world["ids"]["landlord"])
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    db.session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Invalid email or password"


def test_legacy_bcrypt_hashes_remain_verifiable(client, world):
    user = db.session.get(User, world["ids"]["landlord"])

    assert user.password_hash.startswith("$2b$")
    assert len(user.password_hash) == 60
    assert user.check_password("password123")


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


def test_required_totp_blocks_sessions_until_enrollment_and_verification(client, world):
    login_data = start_factor_login(client, "lana@x.com")
    assert login_data["factor_step"] == "email_otp"

    email_verified = verify_email_factor(client, login_data)
    assert email_verified["factor_step"] == "authenticator_enrollment"
    assert client.get("/api/auth/me").status_code == 401
    setup = client.post(
        "/api/auth/two-factor/setup",
        json={"challenge_token": email_verified["challenge_token"]},
    )
    assert setup.status_code == 200
    secret = setup.get_json()["secret"]
    assert setup.get_json()["provisioning_uri"].startswith("otpauth://totp/")

    totp = pyotp.TOTP(secret)
    now_counter = totp.timecode(datetime.now(timezone.utc))
    confirm = client.post(
        "/api/auth/two-factor/confirm",
        json={
            "challenge_token": email_verified["challenge_token"],
            "code": totp.at(now_counter * totp.interval),
        },
    )
    assert confirm.status_code == 200
    assert "access_token" in confirm.get_json()
    user = db.session.get(User, world["ids"]["landlord"])
    assert user.totp_enabled is True
    assert decrypt_totp_secret(user.totp_secret) == secret
    assert user.totp_pending_secret is None
    assert client.get("/api/auth/me", headers=world["landlord"]).status_code == 401

    login_again = start_factor_login(client, "lana@x.com")
    assert client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": login_again["challenge_token"],
            "code": totp.at((now_counter + 1) * totp.interval),
        },
    ).status_code == 401
    totp_challenge = verify_email_factor(client, login_again)
    assert totp_challenge["factor_step"] == "authenticator_totp"
    verify = client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": totp_challenge["challenge_token"],
            "code": totp.at((now_counter + 1) * totp.interval),
        },
    )
    assert verify.status_code == 200
    assert "access_token" in verify.get_json()


def test_required_totp_rejects_unenrolled_existing_sessions(client, world):
    client.application.config["REQUIRE_TWO_FACTOR"] = True
    response = client.get("/api/auth/me", headers=world["landlord"])
    assert response.status_code == 401


def test_legacy_single_factor_jwt_is_rejected(client, world):
    from flask_jwt_extended import create_access_token

    client.application.config["REQUIRE_TWO_FACTOR"] = True
    with client.application.app_context():
        token = create_access_token(
            identity=str(world["ids"]["landlord"]),
            additional_claims={"mfa_verified": True},
        )
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_totp_requires_email_first_and_challenge_is_single_use_and_expires(client, world):
    client.application.config["REQUIRE_TWO_FACTOR"] = True
    enroll_authenticator(client, "lana@x.com")
    user = db.session.get(User, world["ids"]["landlord"])
    totp = pyotp.TOTP(decrypt_totp_secret(user.totp_secret))

    email_challenge = start_factor_login(client, "lana@x.com")
    direct_totp = client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": email_challenge["challenge_token"],
            "code": totp.now(),
        },
    )
    assert direct_totp.status_code == 401
    assert "access_token" not in direct_totp.get_json()

    totp_challenge = verify_email_factor(client, email_challenge)
    counter = totp.timecode(datetime.now(timezone.utc))
    code = totp.at((counter + 1) * totp.interval)
    incorrect = client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": totp_challenge["challenge_token"],
            "code": "000000" if code != "000000" else "000001",
        },
    )
    assert incorrect.status_code == 401
    assert "access_token" not in incorrect.get_json()

    verified = client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": totp_challenge["challenge_token"],
            "code": code,
        },
    )
    assert verified.status_code == 200
    assert verified.get_json()["access_token"]
    replay = client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": totp_challenge["challenge_token"],
            "code": code,
        },
    )
    assert replay.status_code == 401
    assert "access_token" not in replay.get_json()

    next_email_challenge = start_factor_login(client, "lana@x.com")
    next_totp_challenge = verify_email_factor(client, next_email_challenge)
    stored_challenge = AuthFactorChallenge.query.filter_by(
        challenge_hash=challenge_digest(next_totp_challenge["challenge_token"])
    ).one()
    stored_challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    expired = client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": next_totp_challenge["challenge_token"],
            "code": totp.at((counter + 1) * totp.interval),
        },
    )
    assert expired.status_code == 401
    assert "access_token" not in expired.get_json()


def test_google_login_requires_configuration_and_role_for_new_users(client, monkeypatch):
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        GOOGLE_CLIENT_ID="test-client-id",
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "email": "google@example.com",
            "email_verified": True,
            "sub": "google-subject",
            "name": "Google User",
        },
    )

    role_required = client.post(
        "/api/auth/google-login",
        json={"credential": "verified-google-token"},
    )
    assert role_required.status_code == 200
    assert role_required.get_json() == {"role_required": True}

    created = client.post(
        "/api/auth/google-login",
        json={"credential": "verified-google-token", "role": "tenant"},
    )
    data = created.get_json()
    assert created.status_code == 200
    assert data["factor_step"] == "email_otp"
    assert "access_token" not in data
    assert "refresh_token" not in data
    user = User.query.filter_by(email="google@example.com").first()
    assert user is not None
    assert user.password_hash is None
    assert user.role == "tenant"
    assert user.email_verified_at is None



def test_google_login_uses_verified_email_mfa_policy(client, monkeypatch):
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        GOOGLE_CLIENT_ID="test-client-id",
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "email": "google-mfa@example.com",
            "email_verified": True,
            "sub": "google-mfa-subject",
            "name": "Google MFA User",
        },
    )

    response = client.post(
        "/api/auth/google-login",
        json={"credential": "verified-google-token", "role": "tenant"},
    )
    data = response.get_json()
    assert response.status_code == 200
    assert data["mfa_required"] is True
    assert data["factor_step"] == "email_otp"
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert client.get("/api/payments").status_code == 401
    user = User.query.filter_by(email="google-mfa@example.com").one()
    assert user.email_verified_at is None
    email_verified = verify_email_factor(client, data)
    assert email_verified["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in email_verified
    assert "refresh_token" not in email_verified
    assert client.get("/api/payments").status_code == 401
    completed = complete_totp_enrollment(client, email_verified["challenge_token"])
    assert completed["access_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {completed['access_token']}"},
    ).status_code == 200
    assert user.email_verified_at is not None


def test_github_login_requires_state_and_applies_required_mfa(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        GITHUB_CLIENT_ID="github-client-id",
        GITHUB_CLIENT_SECRET="github-client-secret",
        GITHUB_REDIRECT_URI="http://localhost:5173/login",
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    start = client.post("/api/auth/github-login/start", json={})
    assert start.status_code == 200
    authorization_url = start.get_json()["authorization_url"]
    state = parse_qs(urlparse(authorization_url).query)["state"][0]
    assert "user%3Aemail" in authorization_url

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self.payload = payload
            self.status_code = status_code

        def json(self):
            return self.payload

    def fake_post(url, **kwargs):
        assert url == "https://github.com/login/oauth/access_token"
        assert kwargs["data"]["code"] == "one-time-code"
        return FakeResponse({"access_token": "provider-access"})

    def fake_get(url, **kwargs):
        if url == "https://api.github.com/user":
            return FakeResponse({"id": 123, "login": "github-user", "name": None})
        assert url == "https://api.github.com/user/emails"
        return FakeResponse([{
            "email": "github-mfa@example.com",
            "primary": True,
            "verified": True,
        }])

    monkeypatch.setattr(auth.requests, "post", fake_post)
    monkeypatch.setattr(auth.requests, "get", fake_get)
    response = client.post(
        "/api/auth/github-login",
        json={"code": "one-time-code", "state": state, "role": "tenant"},
    )

    data = response.get_json()
    assert response.status_code == 200
    assert data["mfa_required"] is True
    assert data["factor_step"] == "email_otp"
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert client.get("/api/payments").status_code == 401
    user = User.query.filter_by(email="github-mfa@example.com").one()
    assert user.github_sub == "123"
    assert user.email_verified_at is None

    email_verified = verify_email_factor(client, data)
    assert email_verified["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in email_verified
    assert "refresh_token" not in email_verified
    assert client.get("/api/payments").status_code == 401
    completed = complete_totp_enrollment(client, email_verified["challenge_token"])
    assert completed["access_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {completed['access_token']}"},
    ).status_code == 200



def test_github_login_rejects_oauth_state_mismatch(client, monkeypatch):
    from server.routes import auth

    client.application.config.update(
        GITHUB_CLIENT_ID="github-client-id",
        GITHUB_CLIENT_SECRET="github-client-secret",
        GITHUB_REDIRECT_URI="http://localhost:5173/login",
    )
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("OAuth code must not be exchanged"),
    )
    client.post("/api/auth/github-login/start", json={})
    response = client.post(
        "/api/auth/github-login",
        json={"code": "one-time-code", "state": "attacker-state", "role": "tenant"},
    )
    assert response.status_code == 401
    assert "access_token" not in response.get_json()


def complete_totp_enrollment(client, challenge_token):
    setup = client.post(
        "/api/auth/two-factor/setup",
        json={"challenge_token": challenge_token},
    ).get_json()
    totp = pyotp.TOTP(setup["secret"])
    counter = totp.timecode(datetime.now(timezone.utc))
    completed = client.post(
        "/api/auth/two-factor/confirm",
        json={
            "challenge_token": challenge_token,
            "code": totp.at(counter * totp.interval),
        },
    )
    assert completed.status_code == 200
    return completed.get_json()


def enroll_authenticator(client, email):
    challenge = start_factor_login(client, email)
    email_verified = verify_email_factor(client, challenge)
    assert email_verified["factor_step"] == "authenticator_enrollment"
    return complete_totp_enrollment(client, email_verified["challenge_token"])


def email_code_for(challenge_token):
    digest = challenge_digest(challenge_token)
    otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=digest,
        method="email",
    ).one()
    event = (
        EmailOutbox.query.filter(
            EmailOutbox.event_key.contains(f":{digest}:")
        )
        .order_by(EmailOutbox.created_at.desc(), EmailOutbox.id.desc())
        .first()
    )
    assert event is not None
    body = decrypt_mfa_email_body(event.body)
    code = re.search(r"verification code is (\d{6})", body)
    assert code is not None
    assert code.group(1) not in otp.code_hash
    return code.group(1)


def verify_email_factor(client, challenge):
    response = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
            "code": email_code_for(challenge["challenge_token"]),
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" not in data
    assert "refresh_token" not in data
    return data


def start_factor_login(client, email):
    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
        MAIL_SUPPRESS_SEND=False,
    )
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["factor_step"] == "email_otp"
    assert "access_token" not in data
    assert "refresh_token" not in data
    return data


def test_email_code_is_hashed_limited_and_single_use(client, world):
    client.application.config["EMAIL_OTP_TTL_SECONDS"] = 120
    challenge = start_factor_login(client, "lana@x.com")
    otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(challenge["challenge_token"]),
        method="email",
    ).one()
    assert (
        otp.expires_at.replace(tzinfo=timezone.utc)
        - otp.created_at.replace(tzinfo=timezone.utc)
    ).total_seconds() == 120
    code = email_code_for(challenge["challenge_token"])
    assert len(code) == 6 and code.isdigit()
    assert code not in otp.code_hash
    assert "access_token" not in str(otp.code_hash)

    verified = verify_email_factor(client, challenge)
    assert verified["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in verified
    assert "refresh_token" not in verified
    replay = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
            "code": code,
        },
    )
    assert replay.status_code == 401



def test_unverified_email_must_be_verified_before_totp(client, world):
    enroll_authenticator(client, "lana@x.com")
    user = db.session.get(User, world["ids"]["landlord"])
    user.email_verified_at = None
    db.session.commit()

    challenge = start_factor_login(client, "lana@x.com")
    assert user.email_verified_at is None
    verified = verify_email_factor(client, challenge)
    assert verified["factor_step"] == "authenticator_totp"
    assert user.email_verified_at is not None
    assert "access_token" not in verified



def test_first_email_factor_requires_authenticator_before_issuing_jwt(client, world):
    challenge = start_factor_login(client, "lana@x.com")
    assert challenge["factor_step"] == "email_otp"
    assert "access_token" not in challenge
    assert "refresh_token" not in challenge
    assert client.get("/api/payments").status_code == 401

    email_verified = verify_email_factor(client, challenge)
    assert email_verified["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in email_verified
    assert "refresh_token" not in email_verified
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/payments").status_code == 401

    completed = complete_totp_enrollment(client, email_verified["challenge_token"])
    assert completed["access_token"]
    assert completed["refresh_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {completed['access_token']}"},
    ).status_code == 200



def test_email_otp_attempt_limit_and_expiry(client, world):
    import server.routes.auth as auth

    challenge = start_factor_login(client, "lana@x.com")
    code = email_code_for(challenge["challenge_token"])
    incorrect = "000000" if code != "000000" else "000001"

    for _ in range(auth.OTP_MAX_ATTEMPTS):
        response = client.post(
            "/api/auth/two-factor/code/verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "method": "email",
                "code": incorrect,
            },
        )
        assert response.status_code == 401
        assert "access_token" not in response.get_json()

    otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(challenge["challenge_token"]),
        method="email",
    ).one()
    assert otp.attempts == auth.OTP_MAX_ATTEMPTS
    assert otp.consumed_at is not None

    user = db.session.get(User, world["ids"]["landlord"])
    user.failed_login_attempts = 0
    user.login_attempt_window_started_at = None
    user.locked_until = None
    db.session.commit()

    expired_challenge = start_factor_login(client, "lana@x.com")
    expired_otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(expired_challenge["challenge_token"]),
        method="email",
    ).one()
    expired_otp.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    expired = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": expired_challenge["challenge_token"],
            "method": "email",
            "code": email_code_for(expired_challenge["challenge_token"]),
        },
    )
    assert expired.status_code == 401
    assert "access_token" not in expired.get_json()



def test_email_otp_resend_cooldown_and_hourly_limit(client, world, monkeypatch):
    import server.routes.auth as auth

    monkeypatch.setattr(auth.secrets, "randbelow", lambda _upper: 0)
    challenge = start_factor_login(client, "lana@x.com")
    first_code = email_code_for(challenge["challenge_token"])
    request_body = {
        "challenge_token": challenge["challenge_token"],
        "method": "email",
    }
    cooldown = client.post("/api/auth/two-factor/code/send", json=request_body)
    assert cooldown.status_code == 429

    otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(challenge["challenge_token"]),
        method="email",
    ).one()
    otp.created_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    db.session.commit()
    monkeypatch.setattr(auth.secrets, "randbelow", lambda _upper: 1)
    resent = client.post("/api/auth/two-factor/code/send", json=request_body)
    assert resent.status_code == 200
    second_code = email_code_for(challenge["challenge_token"])
    assert second_code != first_code

    old_code = client.post(
        "/api/auth/two-factor/code/verify",
        json={**request_body, "code": first_code},
    )
    assert old_code.status_code == 401
    assert "access_token" not in old_code.get_json()
    accepted = client.post(
        "/api/auth/two-factor/code/verify",
        json={**request_body, "code": second_code},
    )
    assert accepted.status_code == 200
    assert accepted.get_json()["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in accepted.get_json()

    for _ in range(auth.OTP_MAX_PER_HOUR - 2):
        next_login = client.post(
            "/api/auth/login",
            json={"email": "lana@x.com", "password": "password123"},
        )
        assert next_login.status_code == 200
        verify_email_factor(client, next_login.get_json())
    limited = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    assert limited.status_code == 429



def test_mfa_email_outbox_encrypts_code_until_delivery(client):
    body = "Your verification code is 123456."
    queue_email(
        "mfa-code:account:challenge:request",
        "lana@x.com",
        "Sign-in code",
        body,
        encrypt_body=True,
    )
    record = EmailOutbox.query.filter_by(
        event_key="mfa-code:account:challenge:request"
    ).one()

    assert "123456" not in record.body
    assert decrypt_mfa_email_body(record.body) == body
    client.application.config["MAIL_SUPPRESS_SEND"] = True
    assert process_email_outbox()["sent"] == 1
    assert record.body == "[redacted after delivery]"


def test_login_otp_is_delivered_synchronously_and_redacted(client, world, monkeypatch):
    import server.payment_service as payment_service
    from server.routes import auth

    sent = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            pass

        def send_message(self, message):
            sent.append(message.get_content())

    monkeypatch.setattr(payment_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(
        auth,
        "deliver_email_outbox_event",
        payment_service.deliver_email_outbox_event,
    )
    challenge = start_factor_login(client, "lana@x.com")
    match = re.search(r"verification code is (\d{6})", sent[0])
    assert match is not None
    code = match.group(1)
    record = EmailOutbox.query.filter(
        EmailOutbox.event_key.like("mfa-code:%")
    ).one()
    assert record.status == "sent"
    assert record.body == "[redacted after delivery]"
    assert code not in AuthOtpChallenge.query.filter_by(
        challenge_hash=challenge_digest(challenge["challenge_token"])
    ).one().code_hash

    verified = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
            "code": code,
        },
    )
    assert verified.status_code == 200
    assert verified.get_json()["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in verified.get_json()


def test_smtp_failure_does_not_create_an_authenticated_session(
    client, world, monkeypatch
):
    import smtplib
    import server.payment_service as payment_service
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )

    class FailedSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            pass

        def send_message(self, _message):
            raise smtplib.SMTPException("private provider response")

    monkeypatch.setattr(payment_service.smtplib, "SMTP", FailedSMTP)
    monkeypatch.setattr(
        auth,
        "deliver_email_outbox_event",
        payment_service.deliver_email_outbox_event,
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    data = response.get_json()
    assert response.status_code == 503
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "challenge_token" not in data
    assert "private provider response" not in str(data)
    record = EmailOutbox.query.filter(
        EmailOutbox.event_key.like("mfa-code:%")
    ).one()
    assert record.status == "pending"
    assert record.attempts == 1
    assert record.last_error == "SMTPException"
    assert "fernet-v1:" in record.body


def test_recovery_code_requires_email_and_new_authenticator_enrollment(client, world):
    client.application.config["REQUIRE_TWO_FACTOR"] = True
    authenticated = enroll_authenticator(client, "lana@x.com")
    authorization = {"Authorization": f"Bearer {authenticated['access_token']}"}

    generated = client.post("/api/auth/recovery-codes", headers=authorization)
    assert generated.status_code == 200
    codes = generated.get_json()["codes"]
    assert len(codes) == 10
    stored = RecoveryCode.query.filter_by(user_id=world["ids"]["landlord"]).all()
    assert len(stored) == 10
    assert {
        code_digest(world["ids"]["landlord"], "recovery", code.replace("-", ""))
        for code in codes
    } == {item.code_hash for item in stored}

    email_challenge = start_factor_login(client, "lana@x.com")
    email_recovery = client.post(
        "/api/auth/recovery-codes/verify",
        json={
            "challenge_token": email_challenge["challenge_token"],
            "code": "unused-recovery-code",
        },
    )
    assert email_recovery.status_code == 401
    assert "access_token" not in email_recovery.get_json()
    totp_challenge = verify_email_factor(client, email_challenge)
    recovery = client.post(
        "/api/auth/recovery-codes/verify",
        json={
            "challenge_token": totp_challenge["challenge_token"],
            "code": codes[0],
        },
    )
    recovery_data = recovery.get_json()
    assert recovery.status_code == 200
    assert recovery_data["recovery_required"] is True
    assert recovery_data["factor_step"] == "authenticator_enrollment"
    assert "access_token" not in recovery_data
    assert client.get("/api/auth/me").status_code == 401

    replay = client.post(
        "/api/auth/recovery-codes/verify",
        json={
            "challenge_token": totp_challenge["challenge_token"],
            "code": codes[0],
        },
    )
    assert replay.status_code == 401

    completed = complete_totp_enrollment(client, recovery_data["challenge_token"])
    assert completed["access_token"]
    assert any(item.used_at is not None for item in stored)



def test_passkey_registration_options_require_verified_session(client, world):
    client.application.config["REQUIRE_TWO_FACTOR"] = True
    authenticated = enroll_authenticator(client, "lana@x.com")
    registration = client.post(
        "/api/auth/passkeys/registration/options",
        headers={"Authorization": f"Bearer {authenticated['access_token']}"},
    )

    assert registration.status_code == 200
    response = registration.get_json()
    assert response["challenge_token"]
    assert response["options"]["challenge"]
    assert response["options"]["rp"]["id"] == "localhost"


def test_passkey_removal_is_limited_to_the_signed_in_user(client, world):
    client.application.config["REQUIRE_TWO_FACTOR"] = True
    authenticated = enroll_authenticator(client, "lana@x.com")
    credential = PasskeyCredential(
        user_id=world["ids"]["other"],
        credential_id="other-users-passkey",
        public_key="test-public-key",
        name="Other user device",
    )
    db.session.add(credential)
    db.session.commit()

    response = client.delete(
        f"/api/auth/passkeys/{credential.id}",
        headers={"Authorization": f"Bearer {authenticated['access_token']}"},
    )
    assert response.status_code == 404
    assert db.session.get(PasskeyCredential, credential.id) is not None


def test_missing_email_delivery_fails_closed_and_phone_is_not_a_login_factor(
    client, world, monkeypatch
):
    from server.routes import auth

    client.application.config["REQUIRE_TWO_FACTOR"] = True
    authenticated = enroll_authenticator(client, "lana@x.com")
    client.application.config["SMTP_HOST"] = None
    login = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    assert login.status_code == 503
    assert "access_token" not in login.get_json()
    assert "refresh_token" not in login.get_json()

    client.application.config.update(
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    monkeypatch.setattr(auth, "deliver_email_outbox_event", lambda _event_key: False)
    failed_delivery = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    assert failed_delivery.status_code == 503
    assert "access_token" not in failed_delivery.get_json()
    assert "refresh_token" not in failed_delivery.get_json()

    phone = client.post(
        "/api/auth/two-factor/phone/send",
        headers={"Authorization": f"Bearer {authenticated['access_token']}"},
        json={"phone": "+254700000000"},
    )
    assert phone.status_code == 503



def test_phone_verification_cannot_replace_email_or_totp(client, world, monkeypatch):
    import twilio.rest

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN="test-auth-token",
        TWILIO_FROM_NUMBER="+15555550100",
    )
    authenticated = enroll_authenticator(client, "lana@x.com")
    sent_messages = []

    class FakeMessages:
        def create(self, **values):
            sent_messages.append(values)

    class FakeTwilioClient:
        def __init__(self, *_args):
            self.messages = FakeMessages()

    monkeypatch.setattr(twilio.rest, "Client", FakeTwilioClient)
    phone_setup = client.post(
        "/api/auth/two-factor/phone/send",
        headers={"Authorization": f"Bearer {authenticated['access_token']}"},
        json={"phone": "+254700000000"},
    )
    assert phone_setup.status_code == 200
    setup_code = sent_messages[-1]["body"].split("code is ", 1)[1][:6]
    confirmed = client.post(
        "/api/auth/two-factor/phone/verify",
        headers={"Authorization": f"Bearer {authenticated['access_token']}"},
        json={
            "challenge_token": phone_setup.get_json()["challenge_token"],
            "code": setup_code,
        },
    )
    assert confirmed.status_code == 200

    challenge = start_factor_login(client, "lana@x.com")
    assert challenge["factor_step"] == "email_otp"
    passkey_bypass = client.post(
        "/api/auth/passkeys/authentication/options",
        json={},
    )
    assert passkey_bypass.status_code == 403
    sms_bypass = client.post(
        "/api/auth/two-factor/code/send",
        json={"challenge_token": challenge["challenge_token"], "method": "sms"},
    )
    assert sms_bypass.status_code == 401
    email_verified = verify_email_factor(client, challenge)
    assert email_verified["factor_step"] == "authenticator_totp"
    assert "access_token" not in email_verified
