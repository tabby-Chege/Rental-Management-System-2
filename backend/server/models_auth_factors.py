from datetime import datetime, timezone

from server.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class AuthOtpChallenge(db.Model):
    __tablename__ = "auth_otp_challenges"

    id = db.Column(db.Integer, primary_key=True)
    challenge_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    method = db.Column(db.String(12), nullable=False)
    target = db.Column(db.String(255), nullable=True)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class AuthPasskeyChallenge(db.Model):
    __tablename__ = "auth_passkey_challenges"

    id = db.Column(db.Integer, primary_key=True)
    challenge_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(16), nullable=False)
    challenge = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class PasskeyCredential(db.Model):
    __tablename__ = "passkey_credentials"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    credential_id = db.Column(db.String(1024), nullable=False, unique=True)
    public_key = db.Column(db.Text, nullable=False)
    sign_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    name = db.Column(db.String(100), nullable=False, default="Passkey")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)


class RecoveryCode(db.Model):
    __tablename__ = "recovery_codes"
    __table_args__ = (
        db.UniqueConstraint("user_id", "code_hash", name="uq_recovery_code_user_hash"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
