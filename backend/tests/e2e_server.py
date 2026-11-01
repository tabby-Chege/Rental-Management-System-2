import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import create_app
from server.extensions import db


def main():
    with TemporaryDirectory(prefix="rental-e2e-storage-") as storage_path:
        app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": (
                    f"sqlite:///{Path(storage_path) / 'e2e.sqlite3'}"
                ),
                "JWT_SECRET_KEY": "e2e-only-secret-key-at-least-32-characters",
                "REQUIRE_TWO_FACTOR": False,
                "TENANT_PII_ENCRYPTION_KEY": (
                    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
                ),
                "CORS_ORIGINS": [
                    "http://127.0.0.1:5173",
                    "http://localhost:5173",
                ],
                "OBJECT_STORAGE_BACKEND": "local",
                "LOCAL_STORAGE_PATH": storage_path,
                "MAIL_SUPPRESS_SEND": True,
                "PAYMENT_ENVIRONMENT": "sandbox",
            }
        )
        with app.app_context():
            db.create_all()
        app.run(host="127.0.0.1", port=5000, use_reloader=False)


if __name__ == "__main__":
    main()
