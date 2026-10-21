from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    get_jwt,
    jwt_required,
)

from server.decorators import role_required
from server.extensions import db
from server.models import RevokedToken, User


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_BYTES = 72
LOGIN_ERROR = "Invalid email or password"


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

    if isinstance(role, str):
        role = role.strip().lower()
    if role == "admin":
        role = "landlord"
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

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return {
        "message": "User registered successfully",
        "user": user.to_dict(),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }, 201


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

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return {
        "message": "Login successful",
        "user": user.to_dict(),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }, 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    identity = get_jwt_identity()
    revoke_token(claims)

    return {
        "access_token": create_access_token(identity=identity),
        "refresh_token": create_refresh_token(identity=identity),
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
