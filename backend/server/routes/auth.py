import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    get_jwt,
    jwt_required,
)
from cryptography.fernet import Fernet
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
import pyotp
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from server.decorators import role_required
from server.extensions import db
from server.models import RevokedToken, User
from server.models_auth_factors import (
    AuthOtpChallenge,
    AuthPasskeyChallenge,
    PasskeyCredential,
    RecoveryCode,
)
from server.payment_service import queue_email


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_BYTES = 72
LOGIN_ERROR = "Invalid email or password"
FACTOR_CHALLENGE_MAX_AGE_SECONDS = 600
OTP_CHALLENGE_MAX_AGE_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 30
OTP_MAX_PER_HOUR = 5


def factor_serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="required-totp-authentication-v1",
    )


def create_factor_challenge(user, purpose):
    return factor_serializer().dumps({"user_id": user.id, "purpose": purpose})


def read_factor_challenge(token, purpose):
    if not isinstance(token, str) or not token:
        return None
    try:
        payload = factor_serializer().loads(
            token,
            max_age=FACTOR_CHALLENGE_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or payload.get("purpose") != purpose:
        return None
    return db.session.get(User, payload.get("user_id"))


def totp_cipher():
    configured_key = current_app.config.get("TOTP_ENCRYPTION_KEY")
    if configured_key:
        try:
            return Fernet(configured_key.encode("utf-8"))
        except (TypeError, ValueError) as error:
            raise RuntimeError("TOTP_ENCRYPTION_KEY must be a valid Fernet key") from error

    key = hmac.new(
        current_app.config["JWT_SECRET_KEY"].encode("utf-8"),
        b"property-finder-totp-encryption-v1",
        hashlib.sha256,
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_totp_secret(secret):
    return totp_cipher().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_totp_secret(encrypted_secret):
    return totp_cipher().decrypt(encrypted_secret.encode("ascii")).decode("utf-8")


def authenticate_with_totp(user, code):
    if (
        not isinstance(code, str)
        or len(code.strip()) != 6
        or not code.strip().isdigit()
    ):
        return False
    secret = decrypt_totp_secret(user.totp_secret)
    totp = pyotp.TOTP(secret)
    current_counter = totp.timecode(datetime.now(timezone.utc))
    accepted_counter = next(
        (
            counter
            for counter in range(max(0, current_counter - 1), current_counter + 2)
            if hmac.compare_digest(totp.at(counter * totp.interval), code.strip())
        ),
        None,
    )
    if accepted_counter is None or (
        user.totp_last_counter is not None
        and accepted_counter <= user.totp_last_counter
    ):
        return False
    user.totp_last_counter = accepted_counter
    return True


def authentication_response(user, mfa_verified=False):
    return {
        "user": user.to_dict(),
        "access_token": create_access_token(
            identity=str(user.id),
            additional_claims={"mfa_verified": mfa_verified},
        ),
        "refresh_token": create_refresh_token(
            identity=str(user.id),
            additional_claims={"mfa_verified": mfa_verified},
        ),
    }


def factor_required_response(user):
    if user.totp_enabled:
        return {
            "mfa_required": True,
            "challenge_token": create_factor_challenge(user, "verify"),
            "methods": available_factor_methods(user),
        }
    return {
        "mfa_setup_required": True,
        "challenge_token": create_factor_challenge(user, "setup"),
    }


def available_factor_methods(user):
    methods = []
    if user.totp_enabled:
        methods.append({"id": "totp", "label": "Authenticator app"})
    if (
        user.email
        and current_app.config.get("SMTP_HOST")
        and current_app.config.get("SMTP_FROM_ADDRESS")
        and not current_app.config.get("MAIL_SUPPRESS_SEND")
    ):
        methods.append({"id": "email", "label": f"Email ({mask_email(user.email)})"})
    if sms_delivery_configured() and user.mfa_phone_verified and user.mfa_phone:
        methods.append({"id": "sms", "label": f"Text message ({mask_phone(user.mfa_phone)})"})
    if PasskeyCredential.query.filter_by(user_id=user.id).count():
        methods.append({"id": "passkey", "label": "Passkey"})
    if RecoveryCode.query.filter_by(user_id=user.id, used_at=None).count():
        methods.append({"id": "recovery", "label": "Recovery code"})
    return methods


def sms_delivery_configured():
    return all(
        current_app.config.get(key)
        for key in (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_FROM_NUMBER",
        )
    )


def mask_email(email):
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if local and domain else "your email"


def mask_phone(phone):
    return f"••••{phone[-4:]}"


def challenge_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def code_digest(user_id, method, code):
    key = current_app.config["SECRET_KEY"].encode("utf-8")
    value = f"{user_id}:{method}:{code}".encode("utf-8")
    return hmac.new(key, value, hashlib.sha256).hexdigest()


def get_login_factor_user(data):
    user = read_factor_challenge(data.get("challenge_token"), "verify")
    if not user or not user.totp_enabled or not user.totp_secret:
        return None
    now = datetime.now(timezone.utc)
    if user.locked_until and as_utc(user.locked_until) > now:
        return None
    return user


def prune_expired_auth_challenges(now):
    AuthOtpChallenge.query.filter(
        AuthOtpChallenge.expires_at <= now - timedelta(hours=1)
    ).delete(synchronize_session=False)
    AuthPasskeyChallenge.query.filter(
        AuthPasskeyChallenge.expires_at <= now - timedelta(days=1)
    ).delete(synchronize_session=False)


def create_or_replace_otp(user, method, digest, target=None):
    now = datetime.now(timezone.utc)
    prune_expired_auth_challenges(now)
    recent = AuthOtpChallenge.query.filter(
        AuthOtpChallenge.user_id == user.id,
        AuthOtpChallenge.method == method,
        AuthOtpChallenge.created_at >= now - timedelta(hours=1),
    ).order_by(AuthOtpChallenge.created_at.desc()).all()
    if len(recent) >= OTP_MAX_PER_HOUR:
        return None, "Too many verification codes requested. Try again later."
    active = next(
        (
            challenge
            for challenge in recent
            if challenge.consumed_at is None
            and as_utc(challenge.expires_at) > now
        ),
        None,
    )
    if active and now - as_utc(active.created_at) < timedelta(seconds=OTP_RESEND_SECONDS):
        return None, "Please wait before requesting another verification code."
    challenge = AuthOtpChallenge(
        challenge_hash=digest,
        user_id=user.id,
        method=method,
        target=target,
        code_hash="",
        expires_at=now + timedelta(seconds=OTP_CHALLENGE_MAX_AGE_SECONDS),
        attempts=0,
        created_at=now,
    )
    existing = AuthOtpChallenge.query.filter_by(challenge_hash=digest).first()
    if existing:
        existing.method = method
        existing.target = target
        existing.code_hash = ""
        existing.expires_at = challenge.expires_at
        existing.attempts = 0
        existing.consumed_at = None
        existing.created_at = now
        challenge = existing
    else:
        db.session.add(challenge)
    return challenge, None


def issue_otp(user, method, token_digest, target=None):
    code = f"{secrets.randbelow(900000) + 100000}"
    challenge, error = create_or_replace_otp(
        user, method, token_digest, target=target
    )
    if error:
        return None, error
    challenge.code_hash = code_digest(user.id, method, code)
    if method == "email":
        queue_email(
            f"mfa-code:{user.id}:{token_digest}:{challenge.created_at.isoformat()}",
            user.email,
            "Your Property Finder sign-in code",
            f"Your verification code is {code}. It expires in 10 minutes. "
            "If you did not request it, you can ignore this email.",
            encrypt_body=True,
        )
    elif method in {"sms", "phone_setup"}:
        try:
            from twilio.rest import Client
            from twilio.base.exceptions import TwilioException
        except ImportError:
            db.session.rollback()
            current_app.logger.error("Twilio is unavailable for SMS MFA delivery")
            return None, "SMS verification is unavailable on this server."
        try:
            client = Client(
                current_app.config["TWILIO_ACCOUNT_SID"],
                current_app.config["TWILIO_AUTH_TOKEN"],
            )
            client.messages.create(
                body=f"Your Property Finder verification code is {code}. It expires in 10 minutes.",
                from_=current_app.config["TWILIO_FROM_NUMBER"],
                to=target,
            )
        except TwilioException:
            db.session.rollback()
            current_app.logger.error("Twilio could not deliver an MFA code")
            return None, "The text message could not be sent. Try again later."
    db.session.commit()
    return challenge, None


def consume_otp(user, method, token_digest, code):
    now = datetime.now(timezone.utc)
    challenge = db.session.execute(
        select(AuthOtpChallenge)
        .where(
            AuthOtpChallenge.challenge_hash == token_digest,
            AuthOtpChallenge.user_id == user.id,
            AuthOtpChallenge.method == method,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if (
        not challenge
        or challenge.consumed_at is not None
        or as_utc(challenge.expires_at) <= now
        or challenge.attempts >= OTP_MAX_ATTEMPTS
    ):
        return False
    if (
        not isinstance(code, str)
        or not re.fullmatch(r"\d{6}", code)
        or not hmac.compare_digest(challenge.code_hash, code_digest(user.id, method, code))
    ):
        challenge.attempts += 1
        if challenge.attempts >= OTP_MAX_ATTEMPTS:
            challenge.consumed_at = now
        db.session.commit()
        return False
    challenge.consumed_at = now
    return True


def complete_factor_login(user):
    user.failed_login_attempts = 0
    user.login_attempt_window_started_at = None
    user.locked_until = None
    db.session.commit()
    return authentication_response(user, mfa_verified=True), 200


def authenticated_user():
    return db.session.get(User, int(get_jwt_identity()))


def has_verified_mfa_session():
    return get_jwt().get("mfa_verified") is True


def webauthn_configuration():
    return {
        "rp_id": current_app.config["WEBAUTHN_RP_ID"],
        "rp_name": current_app.config["WEBAUTHN_RP_NAME"],
        "origin": current_app.config["WEBAUTHN_ORIGIN"],
    }


def normalize_role(role):
    if isinstance(role, str):
        role = role.strip().lower()
    if role == "admin":
        return "landlord"
    return role


def revoke_token(claims):
    now = datetime.now(timezone.utc)
    RevokedToken.query.filter(RevokedToken.expires_at <= now).delete(
        synchronize_session=False
    )
    db.session.add(
        RevokedToken(
            jti=claims["jti"],
            expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),
        )
    )
    db.session.commit()


def password_validation_error(password):
    if len(password) < PASSWORD_MIN_LENGTH:
        return "Password must be at least 10 characters long"
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return "Password must be no more than 72 UTF-8 bytes"
    if not any(character.islower() for character in password):
        return "Password must include a lowercase letter"
    if not any(character.isupper() for character in password):
        return "Password must include an uppercase letter"
    if not any(character.isdigit() for character in password):
        return "Password must include a number"
    if not any(not character.isalnum() for character in password):
        return "Password must include a symbol"
    return None


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def record_failed_login(user, now):
    lock_until = user.locked_until
    if lock_until and as_utc(lock_until) > now:
        return

    window_started = user.login_attempt_window_started_at
    window_minutes = current_app.config["LOGIN_ATTEMPT_WINDOW_MINUTES"]
    if (
        lock_until
        or not window_started
        or now - as_utc(window_started) >= timedelta(minutes=window_minutes)
    ):
        user.failed_login_attempts = 0
        user.login_attempt_window_started_at = now
        user.locked_until = None

    user.failed_login_attempts += 1
    if user.failed_login_attempts >= current_app.config["LOGIN_MAX_ATTEMPTS"]:
        user.locked_until = now + timedelta(
            minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"]
        )
    db.session.commit()


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "landlord")

    if (
        not isinstance(name, str)
        or not isinstance(email, str)
        or not isinstance(password, str)
    ):
        return {"error": "Name, email, and password are required"}, 400

    role = normalize_role(role)
    if role not in {"landlord", "tenant"}:
        return {"error": "Role must be either landlord or tenant"}, 400
    name = name.strip()
    email = email.strip().lower()
    if not name or not email or not password:
        return {
            "error": "Name, email, and password are required"
        }, 400

    if len(name) > 120 or len(email) > 120:
        return {"error": "Name and email must be 120 characters or fewer"}, 400

    if "@" not in email or "." not in email.split("@")[-1]:
        return {
            "error": "Please provide a valid email address"
        }, 400

    password_error = password_validation_error(password)
    if password_error:
        return {"error": password_error}, 400

    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        return {
            "error": "A user with this email already exists"
        }, 409

    user = User(
        name=name,
        email=email,
        role=role,
    )

    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    response = {
        "message": "User registered successfully",
        "user": user.to_dict(),
    }
    if not current_app.config.get("REQUIRE_TWO_FACTOR"):
        response.update(authentication_response(user))
    return response, 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400

    email = data.get("email")
    password = data.get("password")

    if not isinstance(email, str) or not isinstance(password, str):
        return {"error": "Email and password are required"}, 400

    email = email.strip().lower()
    if not email or not password:
        return {
            "error": "Email and password are required"
        }, 400

    user = User.query.filter_by(email=email).first()

    now = datetime.now(timezone.utc)
    if user:
        lock_until = user.locked_until
        if lock_until and as_utc(lock_until) > now:
            return {"error": LOGIN_ERROR}, 401

        if (
            len(password.encode("utf-8")) > PASSWORD_MAX_BYTES
            or not user.password_hash
            or not user.check_password(password)
        ):
            record_failed_login(user, now)
            return {"error": LOGIN_ERROR}, 401

        user.failed_login_attempts = 0
        user.login_attempt_window_started_at = None
        user.locked_until = None
        db.session.commit()
    else:
        return {"error": LOGIN_ERROR}, 401

    if current_app.config.get("REQUIRE_TWO_FACTOR"):
        return factor_required_response(user), 200
    return {"message": "Login successful", **authentication_response(user)}, 200


@auth_bp.route("/two-factor/setup", methods=["POST"])
def two_factor_setup():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    user = read_factor_challenge(data.get("challenge_token"), "setup")
    if not user or user.totp_enabled:
        return {"error": "The authenticator setup session is invalid or expired"}, 401

    if user.locked_until and as_utc(user.locked_until) > datetime.now(timezone.utc):
        return {"error": LOGIN_ERROR}, 401

    if not user.totp_pending_secret:
        user.totp_pending_secret = encrypt_totp_secret(pyotp.random_base32())
        db.session.commit()

    secret = decrypt_totp_secret(user.totp_pending_secret)
    totp = pyotp.TOTP(secret)
    return {
        "secret": secret,
        "provisioning_uri": totp.provisioning_uri(
            name=user.email,
            issuer_name="Property Finder",
        ),
    }, 200


@auth_bp.route("/two-factor/confirm", methods=["POST"])
def two_factor_confirm():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    user = read_factor_challenge(data.get("challenge_token"), "setup")
    if not user or user.totp_enabled or not user.totp_pending_secret:
        return {"error": "The authenticator setup session is invalid or expired"}, 401

    if user.locked_until and as_utc(user.locked_until) > datetime.now(timezone.utc):
        return {"error": LOGIN_ERROR}, 401

    user.totp_secret = user.totp_pending_secret
    if not authenticate_with_totp(user, data.get("code")):
        user.totp_secret = None
        record_failed_login(user, datetime.now(timezone.utc))
        return {"error": "The authenticator code is invalid"}, 401

    user.totp_enabled = True
    user.totp_pending_secret = None
    user.failed_login_attempts = 0
    user.login_attempt_window_started_at = None
    user.locked_until = None
    db.session.commit()
    return authentication_response(user, mfa_verified=True), 200


@auth_bp.route("/two-factor/verify", methods=["POST"])
def two_factor_verify():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    user = read_factor_challenge(data.get("challenge_token"), "verify")
    if not user or not user.totp_enabled or not user.totp_secret:
        return {"error": "The authentication session is invalid or expired"}, 401

    now = datetime.now(timezone.utc)
    if user.locked_until and as_utc(user.locked_until) > now:
        return {"error": LOGIN_ERROR}, 401
    if not authenticate_with_totp(user, data.get("code")):
        record_failed_login(user, now)
        return {"error": "The authenticator code is invalid"}, 401

    user.failed_login_attempts = 0
    user.login_attempt_window_started_at = None
    user.locked_until = None
    db.session.commit()
    return authentication_response(user, mfa_verified=True), 200


@auth_bp.route("/two-factor/code/send", methods=["POST"])
def send_factor_code():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    user = get_login_factor_user(data)
    method = data.get("method")
    if not user or method not in {"email", "sms"}:
        return {"error": "The authentication session or method is invalid"}, 401
    if method == "sms" and not (user.mfa_phone_verified and user.mfa_phone):
        return {"error": "A verified phone number is not configured"}, 400
    if method == "email":
        if not (
            current_app.config.get("SMTP_HOST")
            and current_app.config.get("SMTP_FROM_ADDRESS")
            and not current_app.config.get("MAIL_SUPPRESS_SEND")
        ):
            return {"error": "Email verification is not configured on this server"}, 503
        target = user.email
    else:
        if not sms_delivery_configured():
            return {"error": "SMS verification is not configured on this server"}, 503
        target = user.mfa_phone

    token_digest = challenge_digest(data["challenge_token"])
    _challenge, error = issue_otp(user, method, token_digest, target=target)
    if error:
        return {"error": error}, 429 if error.startswith(("Too many", "Please wait")) else 503
    delivery = "queued for delivery" if method == "email" else "sent"
    return {"message": f"A verification code was {delivery} by {method}."}, 200


@auth_bp.route("/two-factor/code/verify", methods=["POST"])
def verify_factor_code():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    user = get_login_factor_user(data)
    method = data.get("method")
    if not user or method not in {"email", "sms"}:
        return {"error": "The authentication session or method is invalid"}, 401
    if method == "sms" and not (user.mfa_phone_verified and user.mfa_phone):
        return {"error": "A verified phone number is not configured"}, 400
    token_digest = challenge_digest(data["challenge_token"])
    if not consume_otp(user, method, token_digest, data.get("code")):
        record_failed_login(user, datetime.now(timezone.utc))
        return {"error": "The verification code is invalid or expired"}, 401
    return complete_factor_login(user)


@auth_bp.route("/recovery-codes/verify", methods=["POST"])
def verify_recovery_code():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    user = get_login_factor_user(data)
    code = data.get("code")
    if not user or not isinstance(code, str) or len(code) > 64:
        return {"error": "The authentication session or recovery code is invalid"}, 401

    normalized = code.strip().replace("-", "").upper()
    digest = code_digest(user.id, "recovery", normalized)
    recovery = db.session.execute(
        select(RecoveryCode)
        .where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.code_hash == digest,
            RecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if not recovery:
        record_failed_login(user, datetime.now(timezone.utc))
        return {"error": "The recovery code is invalid or already used"}, 401
    recovery.used_at = datetime.now(timezone.utc)
    return complete_factor_login(user)


@auth_bp.route("/two-factor/methods", methods=["GET"])
@jwt_required()
def get_factor_methods():
    if not has_verified_mfa_session():
        return {"error": "A verified sign-in is required to manage security methods"}, 403
    user = authenticated_user()
    if not user:
        return {"error": "User not found"}, 404
    return {
        "methods": available_factor_methods(user),
        "sms_configured": sms_delivery_configured(),
        "phone_verified": user.mfa_phone_verified,
        "phone": mask_phone(user.mfa_phone) if user.mfa_phone_verified and user.mfa_phone else None,
        "passkeys": [
            {"id": credential.id, "name": credential.name}
            for credential in PasskeyCredential.query.filter_by(user_id=user.id)
            .order_by(PasskeyCredential.created_at.asc())
            .all()
        ],
        "recovery_codes_remaining": RecoveryCode.query.filter_by(
            user_id=user.id, used_at=None
        ).count(),
    }, 200


@auth_bp.route("/two-factor/phone/send", methods=["POST"])
@jwt_required()
def send_phone_setup_code():
    if not has_verified_mfa_session():
        return {"error": "A verified sign-in is required to manage security methods"}, 403
    data = request.get_json(silent=True)
    phone = data.get("phone") if isinstance(data, dict) else None
    if not isinstance(phone, str) or not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
        return {"error": "Enter a valid phone number in international E.164 format"}, 400
    if not sms_delivery_configured():
        return {"error": "SMS verification is not configured on this server"}, 503
    user = authenticated_user()
    if not user:
        return {"error": "User not found"}, 404
    setup_token = secrets.token_urlsafe(32)
    _challenge, error = issue_otp(
        user,
        "phone_setup",
        challenge_digest(setup_token),
        target=phone,
    )
    if error:
        return {"error": error}, 429 if error.startswith(("Too many", "Please wait")) else 503
    return {
        "message": "A verification code was sent to that phone number.",
        "challenge_token": setup_token,
    }, 200


@auth_bp.route("/two-factor/phone/verify", methods=["POST"])
@jwt_required()
def verify_phone_setup_code():
    if not has_verified_mfa_session():
        return {"error": "A verified sign-in is required to manage security methods"}, 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    challenge_token = data.get("challenge_token")
    if not isinstance(challenge_token, str) or not challenge_token:
        return {"error": "A phone verification session is required"}, 400
    user = authenticated_user()
    if not user:
        return {"error": "User not found"}, 404
    token_digest = challenge_digest(challenge_token)
    if not consume_otp(user, "phone_setup", token_digest, data.get("code")):
        return {"error": "The verification code is invalid or expired"}, 401
    challenge = AuthOtpChallenge.query.filter_by(
        challenge_hash=token_digest,
        user_id=user.id,
        method="phone_setup",
    ).first()
    if not challenge or not challenge.target:
        return {"error": "The phone verification session is invalid or expired"}, 401
    user.mfa_phone = challenge.target
    user.mfa_phone_verified = True
    db.session.commit()
    return {"message": "Phone number verified", "phone": mask_phone(user.mfa_phone)}, 200


@auth_bp.route("/recovery-codes", methods=["POST"])
@jwt_required()
def create_recovery_codes():
    if not has_verified_mfa_session():
        return {"error": "A verified sign-in is required to manage security methods"}, 403
    user = authenticated_user()
    if not user:
        return {"error": "User not found"}, 404
    RecoveryCode.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    codes = []
    for _ in range(10):
        raw = secrets.token_hex(8).upper()
        code = f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:]}"
        codes.append(code)
        db.session.add(
            RecoveryCode(
                user_id=user.id,
                code_hash=code_digest(user.id, "recovery", raw),
            )
        )
    db.session.commit()
    return {
        "codes": codes,
        "message": "Save these codes now. They will not be shown again.",
    }, 200


@auth_bp.route("/passkeys/registration/options", methods=["POST"])
@jwt_required()
def begin_passkey_registration():
    if not has_verified_mfa_session():
        return {"error": "A verified sign-in is required to manage security methods"}, 403
    user = authenticated_user()
    if not user:
        return {"error": "User not found"}, 404
    config = webauthn_configuration()
    credentials = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
        for item in PasskeyCredential.query.filter_by(user_id=user.id).all()
    ]
    options = generate_registration_options(
        rp_id=config["rp_id"],
        rp_name=config["rp_name"],
        user_name=user.email,
        user_display_name=user.name,
        user_id=str(user.id).encode("utf-8"),
        exclude_credentials=credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    challenge_token = secrets.token_urlsafe(32)
    prune_expired_auth_challenges(datetime.now(timezone.utc))
    db.session.add(
        AuthPasskeyChallenge(
            challenge_hash=challenge_digest(challenge_token),
            user_id=user.id,
            purpose="register",
            challenge=bytes_to_base64url(options.challenge),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    db.session.commit()
    return {
        "challenge_token": challenge_token,
        "options": json.loads(options_to_json(options)),
    }, 200


@auth_bp.route("/passkeys/registration/complete", methods=["POST"])
@jwt_required()
def complete_passkey_registration():
    if not has_verified_mfa_session():
        return {"error": "A verified sign-in is required to manage security methods"}, 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("credential"), dict):
        return {"error": "A valid passkey credential is required"}, 400
    user = authenticated_user()
    token = data.get("challenge_token")
    challenge = AuthPasskeyChallenge.query.filter_by(
        challenge_hash=challenge_digest(token) if isinstance(token, str) else "",
        user_id=user.id if user else None,
        purpose="register",
        consumed_at=None,
    ).first()
    now = datetime.now(timezone.utc)
    if not user or not challenge or as_utc(challenge.expires_at) <= now:
        return {"error": "The passkey registration session is invalid or expired"}, 401
    config = webauthn_configuration()
    try:
        verification = verify_registration_response(
            credential=data["credential"],
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=config["rp_id"],
            expected_origin=config["origin"],
        )
    except (WebAuthnException, ValueError, TypeError):
        return {"error": "The passkey could not be verified"}, 400
    credential_id = bytes_to_base64url(verification.credential_id)
    if PasskeyCredential.query.filter_by(credential_id=credential_id).first():
        return {"error": "This passkey is already registered"}, 409
    name = data.get("name", "Passkey")
    if not isinstance(name, str):
        return {"error": "Passkey name must be text"}, 400
    name = name.strip()[:100] or "Passkey"
    db.session.add(
        PasskeyCredential(
            user_id=user.id,
            credential_id=credential_id,
            public_key=bytes_to_base64url(verification.credential_public_key),
            sign_count=verification.sign_count,
            name=name,
        )
    )
    challenge.consumed_at = now
    db.session.commit()
    return {"message": "Passkey added", "name": name}, 201


@auth_bp.route("/passkeys/<int:credential_id>", methods=["DELETE"])
@jwt_required()
def delete_passkey(credential_id):
    if not has_verified_mfa_session():
        return {"error": "A verified sign-in is required to manage security methods"}, 403
    user = authenticated_user()
    credential = PasskeyCredential.query.filter_by(
        id=credential_id,
        user_id=user.id if user else None,
    ).first()
    if not credential:
        return {"error": "Passkey not found"}, 404
    db.session.delete(credential)
    db.session.commit()
    return {"message": "Passkey removed"}, 200


@auth_bp.route("/passkeys/authentication/options", methods=["POST"])
def begin_passkey_authentication():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    user = get_login_factor_user(data)
    if not user:
        return {"error": "The authentication session is invalid or expired"}, 401
    credentials = PasskeyCredential.query.filter_by(user_id=user.id).all()
    if not credentials:
        return {"error": "No passkey is configured for this account"}, 400
    config = webauthn_configuration()
    options = generate_authentication_options(
        rp_id=config["rp_id"],
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in credentials
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_token = secrets.token_urlsafe(32)
    prune_expired_auth_challenges(datetime.now(timezone.utc))
    db.session.add(
        AuthPasskeyChallenge(
            challenge_hash=challenge_digest(challenge_token),
            user_id=user.id,
            purpose="login",
            challenge=bytes_to_base64url(options.challenge),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    db.session.commit()
    return {
        "challenge_token": challenge_token,
        "options": json.loads(options_to_json(options)),
    }, 200


@auth_bp.route("/passkeys/authentication/complete", methods=["POST"])
def complete_passkey_authentication():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("credential"), dict):
        return {"error": "A valid passkey credential is required"}, 400
    login_token = data.get("login_challenge_token")
    user = read_factor_challenge(login_token, "verify")
    passkey_token = data.get("passkey_challenge_token")
    challenge = AuthPasskeyChallenge.query.filter_by(
        challenge_hash=challenge_digest(passkey_token) if isinstance(passkey_token, str) else "",
        user_id=user.id if user else None,
        purpose="login",
        consumed_at=None,
    ).first()
    now = datetime.now(timezone.utc)
    if (
        not user
        or not user.totp_enabled
        or not challenge
        or as_utc(challenge.expires_at) <= now
    ):
        return {"error": "The passkey sign-in session is invalid or expired"}, 401
    credential_payload = data["credential"]
    credential_id = credential_payload.get("id")
    credential = (
        PasskeyCredential.query.filter_by(
            user_id=user.id,
            credential_id=credential_id,
        ).first()
        if isinstance(credential_id, str)
        else None
    )
    if not credential:
        return {"error": "This passkey is not registered"}, 401
    config = webauthn_configuration()
    try:
        verification = verify_authentication_response(
            credential=credential_payload,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=config["rp_id"],
            expected_origin=config["origin"],
            credential_public_key=base64url_to_bytes(credential.public_key),
            credential_current_sign_count=credential.sign_count,
        )
    except (WebAuthnException, ValueError, TypeError):
        record_failed_login(user, now)
        return {"error": "The passkey could not be verified"}, 401
    credential.sign_count = verification.new_sign_count
    credential.last_used_at = now
    challenge.consumed_at = now
    return complete_factor_login(user)


@auth_bp.route("/google-login", methods=["POST"])
def google_login():
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    if not client_id:
        return {"error": "Google sign-in is not configured"}, 503
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    credential = data.get("credential")
    if not isinstance(credential, str) or not credential:
        return {"error": "A Google credential is required"}, 400

    try:
        claims = id_token.verify_oauth2_token(
            credential,
            GoogleRequest(),
            client_id,
        )
    except (ValueError, GoogleAuthError):
        return {"error": "Google sign-in could not be verified"}, 401

    email = claims.get("email")
    google_sub = claims.get("sub")
    name = claims.get("name")
    if (
        claims.get("email_verified") is not True
        or not isinstance(email, str)
        or not isinstance(google_sub, str)
        or not google_sub
        or not isinstance(name, str)
    ):
        return {"error": "Google did not provide a verified account"}, 401
    email = email.strip().lower()
    name = name.strip()
    if not email or len(email) > 120 or not name or len(name) > 120:
        return {"error": "Google account details are invalid"}, 400

    user = User.query.filter_by(google_sub=google_sub).first()
    email_user = User.query.filter_by(email=email).first()
    if user and email_user and user.id != email_user.id:
        return {"error": "This Google account cannot be linked to that email"}, 409
    if not user:
        user = email_user
        if user and user.google_sub and user.google_sub != google_sub:
            return {"error": "A different Google account is already linked"}, 409

    if not user:
        role = normalize_role(data.get("role"))
        if role not in {"landlord", "tenant"}:
            return {"role_required": True}, 200
        user = User(
            name=name,
            email=email,
            role=role,
            google_sub=google_sub,
        )
        db.session.add(user)
    elif not user.google_sub:
        user.google_sub = google_sub
    db.session.commit()

    if current_app.config.get("REQUIRE_TWO_FACTOR"):
        return factor_required_response(user), 200
    return {"message": "Login successful", **authentication_response(user)}, 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    identity = get_jwt_identity()
    revoke_token(claims)
    mfa_claims = {"mfa_verified": claims.get("mfa_verified") is True}

    return {
        "access_token": create_access_token(
            identity=identity,
            additional_claims=mfa_claims,
        ),
        "refresh_token": create_refresh_token(
            identity=identity,
            additional_claims=mfa_claims,
        ),
    }, 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required(refresh=True)
def logout():
    revoke_token(get_jwt())
    return {"message": "Signed out successfully"}, 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    user_id = get_jwt_identity()

    user = db.session.get(User, user_id)

    if not user:
        return {
            "error": "User not found"
        }, 404

    return {
        "user": user.to_dict()
    }, 200


@auth_bp.route("/admin-test", methods=["GET"])
@role_required("admin")
def admin_test():
    return {
        "message": "You have admin access"
    }, 200
