import os
import subprocess
import sys
from pathlib import Path

from server import create_app
from server.extensions import db
from server.models import Property, User
from server.models_unit_lease import Unit

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = BACKEND_ROOT / "scripts" / "seed_demo_properties.py"


def test_demo_seed_adds_sample_properties_idempotently(tmp_path):
    database_path = tmp_path / "rental-demo.sqlite3"
    database_url = f"sqlite:///{database_path}"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": database_url,
            "JWT_SECRET_KEY": "demo-seed-test-secret-at-least-32-characters",
            "REQUIRE_TWO_FACTOR": False,
            "TENANT_PII_ENCRYPTION_KEY": (
                "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
            ),
        }
    )
    with app.app_context():
        db.create_all()

    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "JWT_SECRET_KEY": "demo-seed-test-secret-at-least-32-characters",
            "CORS_ORIGINS": "http://localhost:5173",
            "APP_ENV": "development",
            "ENABLE_DEMO_DATA": "true",
            "DEMO_LANDLORD_PASSWORD": "DemoSeedTest123!",
        }
    )
    command = [
        sys.executable,
        str(SEED_SCRIPT),
        "--confirm-development-data",
    ]

    first_run = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first_run.returncode == 0, first_run.stderr
    assert "created 12 sample properties" in first_run.stdout

    second_run = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second_run.returncode == 0, second_run.stderr
    assert "created 0 sample properties; 12 already existed" in second_run.stdout

    with app.app_context():
        landlord = User.query.filter_by(email="demo-landlord@example.test").one()
        assert landlord.role == "landlord"
        assert Property.query.filter_by(owner_id=landlord.id).count() == 12
        assert Unit.query.join(Property).filter(Property.owner_id == landlord.id).count() == 12
