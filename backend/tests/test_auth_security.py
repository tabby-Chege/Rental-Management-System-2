from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from server.extensions import db
from server.models import User
from server.models_auth_factors import AuthOtpChallenge, PasskeyCredential, RecoveryCode
from server.models_payment import EmailOutbox
from server.payment_service import (
    decrypt_mfa_email_body,
    process_email_outbox,
    queue_email,
)
from server.routes.auth import code_digest, decrypt_totp_secret
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


def test_required_totp_blocks_sessions_until_enrollment_and_verification(client, world):
    client.application.config["REQUIRE_TWO_FACTOR"] = True

    login = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    assert login.status_code == 200
    login_data = login.get_json()
    assert login_data["mfa_setup_required"] is True
    assert "access_token" not in login_data

    setup = client.post(
        "/api/auth/two-factor/setup",
        json={"challenge_token": login_data["challenge_token"]},
    )
    assert setup.status_code == 200
    secret = setup.get_json()["secret"]
    assert setup.get_json()["provisioning_uri"].startswith("otpauth://totp/")

    totp = pyotp.TOTP(secret)
    now_counter = totp.timecode(datetime.now(timezone.utc))
    confirm = client.post(
        "/api/auth/two-factor/confirm",
        json={
            "challenge_token": login_data["challenge_token"],
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

    login_again = client.post(
        "/api/auth/login",
        json={"email": "lana@x.com", "password": "password123"},
    )
    assert login_again.get_json()["mfa_required"] is True
    verify = client.post(
        "/api/auth/two-factor/verify",
        json={
            "challenge_token": login_again.get_json()["challenge_token"],
            "code": totp.at((now_counter + 1) * totp.interval),
        },
    )
    assert verify.status_code == 200
    assert "access_token" in verify.get_json()


def test_required_totp_rejects_unenrolled_existing_sessions(client, world):
    client.application.config["REQUIRE_TWO_FACTOR"] = True
    response = client.get("/api/auth/me", headers=world["landlord"])
    assert response.status_code == 401


def test_google_login_requires_configuration_and_role_for_new_users(client, monkeypatch):
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        GOOGLE_CLIENT_ID="test-client-id",
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
    assert created.status_code == 200
    assert created.get_json()["mfa_setup_required"] is True
    user = User.query.filter_by(email="google@example.com").first()
    assert user is not None
    assert user.password_hash is None
    assert user.role == "tenant"


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
    assert data["methods"][0]["id"] == "email"
    assert "access_token" not in data
    user = User.query.filter_by(email="google-mfa@example.com").one()
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
        assert kwargs["headers"]["Authorization"] == "Bearer provider-access"
        if url == "https://api.github.com/user":
            return FakeResponse({"id": 123, "login": "github-user", "name": None})
        assert url == "https://api.github.com/user/emails"
        return FakeResponse(
            [
                {
                    "email": "github-mfa@example.com",
                    "primary": True,
                    "verified": True,
                }
            ]
        )

    monkeypatch.setattr(auth.requests, "post", fake_post)
    monkeypatch.setattr(auth.requests, "get", fake_get)
    response = client.post(
        "/api/auth/github-login",
        json={"code": "one-time-code", "state": state, "role": "tenant"},
    )

    data = response.get_json()
    assert response.status_code == 200
    assert data["mfa_required"] is True
    assert data["methods"][0]["id"] == "email"
    assert "access_token" not in data
    user = User.query.filter_by(email="github-mfa@example.com").one()
    assert user.github_sub == "123"
    assert user.email_verified_at is not None

    sent = []
    monkeypatch.setattr(
        auth,
        "queue_email",
        lambda *args, **kwargs: sent.append(args),
    )
    requested = client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": data["challenge_token"],
            "method": "email",
        },
    )
    assert requested.status_code == 200
    code = sent[0][3].split("Your verification code is ", 1)[1][:6]
    completed = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": data["challenge_token"],
            "method": "email",
            "code": code,
        },
    )
    assert completed.status_code == 200
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {completed.get_json()['access_token']}"},
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


def enroll_authenticator(client, email):
    challenge = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    ).get_json()
    setup = client.post(
        "/api/auth/two-factor/setup",
        json={"challenge_token": challenge["challenge_token"]},
    ).get_json()
    totp = pyotp.TOTP(setup["secret"])
    counter = totp.timecode(datetime.now(timezone.utc))
    completed = client.post(
        "/api/auth/two-factor/confirm",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": totp.at(counter * totp.interval),
        },
    )
    assert completed.status_code == 200
    return completed.get_json()


def start_factor_login(client, email):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return response.get_json()


def test_email_code_is_hashed_limited_and_single_use(client, world, monkeypatch):
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    enroll_authenticator(client, "lana@x.com")
    user = db.session.get(User, world["ids"]["landlord"])
    user.email_verified_at = datetime.now(timezone.utc)
    db.session.commit()
    challenge = start_factor_login(client, "lana@x.com")
    sent = []
    monkeypatch.setattr(
        auth,
        "queue_email",
        lambda *args, **kwargs: sent.append(args),
    )

    methods = challenge["methods"]
    assert {method["id"] for method in methods} >= {"totp", "email"}
    requested = client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
        },
    )
    assert requested.status_code == 200
    code = sent[0][3].split("Your verification code is ", 1)[1][:6]
    otp = auth.AuthOtpChallenge.query.one()
    assert code not in otp.code_hash
    assert code not in str(requested.get_json())
    assert (
        auth.as_utc(otp.expires_at) - auth.as_utc(otp.created_at)
    ).total_seconds() == 300

    verified = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
            "code": code,
        },
    )
    assert verified.status_code == 200
    assert verified.get_json()["user"]["email"] == "lana@x.com"
    refreshed = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {verified.get_json()['refresh_token']}"},
    )
    assert refreshed.status_code == 200
    methods_after_refresh = client.get(
        "/api/auth/two-factor/methods",
        headers={"Authorization": f"Bearer {refreshed.get_json()['access_token']}"},
    )
    assert methods_after_refresh.status_code == 200
    methods_data = methods_after_refresh.get_json()
    assert methods_data["sms_configured"] is False
    assert all(method["id"] != "sms" for method in methods_data["methods"])
    assert client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
            "code": code,
        },
    ).status_code == 401
    assert client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
        },
    ).status_code == 401


def test_unverified_email_is_not_an_email_factor_for_totp_users(client, world):
    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    enroll_authenticator(client, "lana@x.com")
    challenge = start_factor_login(client, "lana@x.com")

    assert "email" not in {method["id"] for method in challenge["methods"]}
    sent = client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
        },
    )
    assert sent.status_code == 400
    assert "verified email" in sent.get_json()["error"]


def test_first_email_factor_verifies_email_and_issues_jwt_only_after_code(
    client, world, monkeypatch
):
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    challenge = start_factor_login(client, "lana@x.com")
    data = challenge
    assert data["mfa_required"] is True
    assert data["methods"] == [
        {"id": "email", "label": "Verify email (l***@x.com)"}
    ]
    assert "access_token" not in data

    sent = []
    monkeypatch.setattr(
        auth,
        "queue_email",
        lambda *args, **kwargs: sent.append(args),
    )
    requested = client.post(
        "/api/auth/two-factor/code/send",
        json={"challenge_token": data["challenge_token"], "method": "email"},
    )
    assert requested.status_code == 200
    code = sent[0][3].split("Your verification code is ", 1)[1][:6]
    assert code not in str(requested.get_json())

    verified = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": data["challenge_token"],
            "method": "email",
            "code": code,
        },
    )
    assert verified.status_code == 200
    assert verified.get_json()["access_token"]
    user = db.session.get(User, world["ids"]["landlord"])
    assert user.email_verified_at is not None
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {verified.get_json()['access_token']}"},
    ).status_code == 200


def test_email_otp_attempt_limit_and_expiry(client, world, monkeypatch):
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    user = db.session.get(User, world["ids"]["landlord"])
    user.email_verified_at = datetime.now(timezone.utc)
    db.session.commit()
    challenge = start_factor_login(client, "lana@x.com")
    sent = []
    monkeypatch.setattr(
        auth,
        "queue_email",
        lambda *args, **kwargs: sent.append(args),
    )
    client.post(
        "/api/auth/two-factor/code/send",
        json={"challenge_token": challenge["challenge_token"], "method": "email"},
    )
    otp = AuthOtpChallenge.query.one()

    for _ in range(auth.OTP_MAX_ATTEMPTS):
        invalid = client.post(
            "/api/auth/two-factor/code/verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "method": "email",
                "code": "000000",
            },
        )
        assert invalid.status_code == 401
        assert "access_token" not in invalid.get_json()
    db.session.refresh(otp)
    assert otp.attempts == auth.OTP_MAX_ATTEMPTS
    assert otp.consumed_at is not None

    user.failed_login_attempts = 0
    user.login_attempt_window_started_at = None
    user.locked_until = None
    db.session.commit()
    second_challenge = start_factor_login(client, "lana@x.com")
    client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": second_challenge["challenge_token"],
            "method": "email",
        },
    )
    otp = AuthOtpChallenge.query.filter_by(
        challenge_hash=auth.challenge_digest(second_challenge["challenge_token"])
    ).one()
    otp.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    expired = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": second_challenge["challenge_token"],
            "method": "email",
            "code": sent[-1][3].split("Your verification code is ", 1)[1][:6],
        },
    )
    assert expired.status_code == 401
    assert "access_token" not in expired.get_json()


def test_email_otp_resend_cooldown_and_hourly_limit(client, world, monkeypatch):
    from server.routes import auth

    client.application.config.update(
        REQUIRE_TWO_FACTOR=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_ADDRESS="security@example.com",
    )
    user = db.session.get(User, world["ids"]["landlord"])
    user.email_verified_at = datetime.now(timezone.utc)
    db.session.commit()
    challenge = start_factor_login(client, "lana@x.com")
    sent = []
    monkeypatch.setattr(
        auth,
        "queue_email",
        lambda *args, **kwargs: sent.append(args),
    )
    request_body = {
        "challenge_token": challenge["challenge_token"],
        "method": "email",
    }
    assert client.post("/api/auth/two-factor/code/send", json=request_body).status_code == 200
    cooldown = client.post("/api/auth/two-factor/code/send", json=request_body)
    assert cooldown.status_code == 429
    assert "wait" in cooldown.get_json()["error"].lower()

    otp = AuthOtpChallenge.query.one()
    otp.created_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    db.session.commit()
    resent = client.post("/api/auth/two-factor/code/send", json=request_body)
    assert resent.status_code == 200
    assert len(sent) == 2
    assert sent[0][3] != sent[1][3]

    for _ in range(auth.OTP_MAX_PER_HOUR - 1):
        challenge = start_factor_login(client, "lana@x.com")
        AuthOtpChallenge.query.filter_by(
            challenge_hash=auth.challenge_digest(challenge["challenge_token"])
        ).delete()
        db.session.commit()
        client.post(
            "/api/auth/two-factor/code/send",
            json={
                "challenge_token": challenge["challenge_token"],
                "method": "email",
            },
        )
    limited = client.post(
        "/api/auth/two-factor/code/send",
        json=request_body,
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


def test_recovery_codes_are_returned_once_and_consumed(client, world):
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
        code_digest(
            world["ids"]["landlord"],
            "recovery",
            code.replace("-", ""),
        )
        for code in codes
    } == {item.code_hash for item in stored}

    challenge = start_factor_login(client, "lana@x.com")
    verified = client.post(
        "/api/auth/recovery-codes/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": codes[0],
        },
    )
    assert verified.status_code == 200
    replay = client.post(
        "/api/auth/recovery-codes/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": codes[0],
        },
    )
    assert replay.status_code == 401


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


def test_email_factor_and_phone_setup_report_missing_delivery_configuration(
    client, world
):
    client.application.config["REQUIRE_TWO_FACTOR"] = True
    authenticated = enroll_authenticator(client, "lana@x.com")
    challenge = start_factor_login(client, "lana@x.com")

    email = client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "email",
        },
    )
    assert email.status_code == 503
    assert "not configured" in email.get_json()["error"]

    phone = client.post(
        "/api/auth/two-factor/phone/send",
        headers={"Authorization": f"Bearer {authenticated['access_token']}"},
        json={"phone": "+254700000000"},
    )
    assert phone.status_code == 503
    assert "not configured" in phone.get_json()["error"]


def test_twilio_phone_setup_enables_sms_login_factor(client, world, monkeypatch):
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
    assert sent_messages[-1]["to"] == "+254700000000"
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
    assert "sms" in {method["id"] for method in challenge["methods"]}
    sent = client.post(
        "/api/auth/two-factor/code/send",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "sms",
        },
    )
    assert sent.status_code == 200
    login_code = sent_messages[-1]["body"].split("code is ", 1)[1][:6]
    verified = client.post(
        "/api/auth/two-factor/code/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "method": "sms",
            "code": login_code,
        },
    )
    assert verified.status_code == 200
