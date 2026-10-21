import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    @classmethod
    def load(cls):
        jwt_secret = os.getenv("JWT_SECRET_KEY")
        s3_bucket = os.getenv("S3_BUCKET")
        return {
            "SQLALCHEMY_DATABASE_URI": (
                os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL")
            ),
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "JWT_SECRET_KEY": jwt_secret,
            "SECRET_KEY": jwt_secret,
            "JWT_ACCESS_TOKEN_EXPIRES": timedelta(minutes=15),
            "JWT_REFRESH_TOKEN_EXPIRES": timedelta(days=30),
            "LOGIN_MAX_ATTEMPTS": 5,
            "LOGIN_ATTEMPT_WINDOW_MINUTES": 15,
            "LOGIN_LOCKOUT_MINUTES": 15,
            "REQUIRE_TWO_FACTOR": os.getenv("REQUIRE_TWO_FACTOR", "true").lower()
            == "true",
            "TOTP_ENCRYPTION_KEY": os.getenv("TOTP_ENCRYPTION_KEY"),
            "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
            "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID"),
            "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN"),
            "TWILIO_FROM_NUMBER": os.getenv("TWILIO_FROM_NUMBER"),
            "WEBAUTHN_RP_ID": os.getenv("WEBAUTHN_RP_ID", "localhost"),
            "WEBAUTHN_RP_NAME": os.getenv(
                "WEBAUTHN_RP_NAME", "Property Finder"
            ),
            "WEBAUTHN_ORIGIN": os.getenv(
                "WEBAUTHN_ORIGIN", "http://localhost:5173"
            ),
            "TENANT_PII_ENCRYPTION_KEY": os.getenv(
                "TENANT_PII_ENCRYPTION_KEY"
            ),
            "OBJECT_STORAGE_BACKEND": os.getenv(
                "OBJECT_STORAGE_BACKEND", "s3" if s3_bucket else "local"
            ).strip().lower(),
            "LOCAL_STORAGE_PATH": os.getenv("LOCAL_STORAGE_PATH")
            or os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "instance",
                "object-storage",
            ),
            "S3_BUCKET": s3_bucket,
            "S3_REGION": os.getenv("S3_REGION", "us-east-1"),
            "S3_ENDPOINT_URL": os.getenv("S3_ENDPOINT_URL"),
            "S3_SERVER_SIDE_ENCRYPTION": os.getenv(
                "S3_SERVER_SIDE_ENCRYPTION", "AES256"
            ),
            "PAYMENT_ENVIRONMENT": os.getenv("PAYMENT_ENVIRONMENT", "sandbox"),
            "BANK_TRANSFER_INSTRUCTIONS": os.getenv(
                "BANK_TRANSFER_INSTRUCTIONS", ""
            ),
            "FRONTEND_BASE_URL": os.getenv(
                "FRONTEND_BASE_URL", "http://localhost:5173"
            ).rstrip("/"),
            "STRIPE_SECRET_KEY": os.getenv("STRIPE_SECRET_KEY"),
            "STRIPE_WEBHOOK_SECRET": os.getenv("STRIPE_WEBHOOK_SECRET"),
            "PAYPAL_CLIENT_ID": os.getenv("PAYPAL_CLIENT_ID"),
            "PAYPAL_CLIENT_SECRET": os.getenv("PAYPAL_CLIENT_SECRET"),
            "PAYPAL_WEBHOOK_ID": os.getenv("PAYPAL_WEBHOOK_ID"),
            "DARAJA_CONSUMER_KEY": os.getenv("DARAJA_CONSUMER_KEY"),
            "DARAJA_CONSUMER_SECRET": os.getenv("DARAJA_CONSUMER_SECRET"),
            "DARAJA_SHORTCODE": os.getenv("DARAJA_SHORTCODE"),
            "DARAJA_PASSKEY": os.getenv("DARAJA_PASSKEY"),
            "DARAJA_CALLBACK_URL": os.getenv("DARAJA_CALLBACK_URL"),
            "FLUTTERWAVE_SECRET_KEY": os.getenv("FLUTTERWAVE_SECRET_KEY"),
            "FLUTTERWAVE_WEBHOOK_HASH": os.getenv("FLUTTERWAVE_WEBHOOK_HASH"),
            "PESAPAL_CONSUMER_KEY": os.getenv("PESAPAL_CONSUMER_KEY"),
            "PESAPAL_CONSUMER_SECRET": os.getenv("PESAPAL_CONSUMER_SECRET"),
            "PESAPAL_CALLBACK_URL": os.getenv("PESAPAL_CALLBACK_URL"),
            "PESAPAL_IPN_ID": os.getenv("PESAPAL_IPN_ID"),
            "SMTP_HOST": os.getenv("SMTP_HOST"),
            "SMTP_PORT": int(os.getenv("SMTP_PORT", "587")),
            "SMTP_USERNAME": os.getenv("SMTP_USERNAME"),
            "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD"),
            "SMTP_FROM_ADDRESS": os.getenv("SMTP_FROM_ADDRESS"),
            "SMTP_USE_TLS": os.getenv("SMTP_USE_TLS", "true").lower() == "true",
            "MAIL_SUPPRESS_SEND": os.getenv("MAIL_SUPPRESS_SEND", "false").lower()
            == "true",
            "TENANT_DOCUMENT_MAX_BYTES": 10 * 1024 * 1024,
            "PROPERTY_PHOTO_MAX_BYTES": 10 * 1024 * 1024,
            "MAX_CONTENT_LENGTH": 11 * 1024 * 1024,
            "CORS_ORIGINS": [
                origin.strip()
                for origin in os.getenv(
                    "CORS_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173",
                ).split(",")
                if origin.strip()
            ],
            # Hosted PostgreSQL may close idle connections; test pooled
            # connections before use and recycle old ones.
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "pool_pre_ping": True,
                "pool_recycle": 280,
            },
        }
