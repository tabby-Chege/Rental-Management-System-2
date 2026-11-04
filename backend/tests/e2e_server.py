import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import create_app
from server.extensions import db
from server.models_payment import EmailOutbox
from server.payment_service import decrypt_mfa_email_body


test_otp_codes = {}


def capture_test_email(event_key):
    message = EmailOutbox.query.filter_by(event_key=event_key).one_or_none()
    if not message:
        return False
    body = decrypt_mfa_email_body(message.body)
    match = re.search(r"verification code is (\d{6})", body)
    if not match:
        return False
    test_otp_codes[message.recipient] = match.group(1)
    return True


def main():
    with TemporaryDirectory(prefix="rental-e2e-storage-") as storage_path:
        app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": (
                    f"sqlite:///{Path(storage_path) / 'e2e.sqlite3'}"
                ),
                "JWT_SECRET_KEY": "e2e-only-secret-key-at-least-32-characters",
                "REQUIRE_TWO_FACTOR": True,
                "TOTP_ENCRYPTION_KEY": None,
                "TENANT_PII_ENCRYPTION_KEY": (
                    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
                ),
                "CORS_ORIGINS": [
                    "http://127.0.0.1:5173",
                    "http://localhost:5173",
                    "http://127.0.0.1:5174",
                    "http://localhost:5174",
                ],
                "OBJECT_STORAGE_BACKEND": "local",
                "LOCAL_STORAGE_PATH": storage_path,
                "MAIL_SUPPRESS_SEND": False,
                "SMTP_HOST": "test-smtp.invalid",
                "SMTP_FROM_ADDRESS": "security@example.test",
                "PAYMENT_ENVIRONMENT": "sandbox",
            }
        )
        from server.routes import auth

        auth.deliver_email_outbox_event = capture_test_email

        @app.get("/__test__/email-otp")
        def get_test_email_otp():
            email = request.args.get("email", "").strip().lower()
            code = test_otp_codes.pop(email, None)
            if not code:
                return {"error": "No test email code is available"}, 404
            return {"code": code}, 200

        with app.app_context():
            db.create_all()
        app.run(host="127.0.0.1", port=5000, use_reloader=False)


if __name__ == "__main__":
    main()
