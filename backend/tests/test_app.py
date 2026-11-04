from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token

from server import create_app
from server.extensions import db
from server.models import User
from tests.db_safety import TEST_DATABASE_URI, assert_isolated_test_database


def test_app_requires_database_and_long_jwt_secret(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app()

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        create_app()


def test_production_app_rejects_disabled_two_factor():
    with pytest.raises(RuntimeError, match="Two-factor authentication is mandatory"):
        create_app(
            {
                "TESTING": False,
                "REQUIRE_TWO_FACTOR": False,
                "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URI,
                "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
            }
        )


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://localhost/rental_management",
        "postgresql://localhost/rental_management_rehearsal_20261102",
        "sqlite:////tmp/rental-test.db",
    ],
)
def test_destructive_test_guard_rejects_non_memory_databases(uri):
    app = SimpleNamespace(
        testing=True,
        config={"SQLALCHEMY_DATABASE_URI": uri},
    )

    with pytest.raises(RuntimeError, match="explicit in-memory SQLite"):
        assert_isolated_test_database(app)


def test_cors_only_allows_configured_frontend_origin():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URI,
            "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
            "CORS_ORIGINS": ["https://rentals.example"],
        }
    )
    client = app.test_client()

    allowed = client.get(
        "/api/health",
        headers={"Origin": "https://rentals.example"},
    )
    denied = client.get(
        "/api/health",
        headers={"Origin": "https://untrusted.example"},
    )
    checkout_preflight = client.options(
        "/api/payments/checkout",
        headers={
            "Origin": "https://rentals.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "authorization,content-type,idempotency-key"
            ),
        },
    )

    assert allowed.headers["Access-Control-Allow-Origin"] == "https://rentals.example"
    assert "Access-Control-Allow-Origin" not in denied.headers
    assert checkout_preflight.headers["Access-Control-Allow-Origin"] == (
        "https://rentals.example"
    )
    assert "idempotency-key" in checkout_preflight.headers[
        "Access-Control-Allow-Headers"
    ].lower()


def test_http_errors_use_json_error_shape():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URI,
            "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
        }
    )

    response = app.test_client().get("/missing")

    assert response.status_code == 404
    assert set(response.get_json()) == {"error"}


def test_jwt_validation_uses_the_requesting_app_configuration():
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URI,
        "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
        "REQUIRE_TWO_FACTOR": False,
    }
    first_app = create_app(test_config)
    with first_app.app_context():
        assert_isolated_test_database(first_app)
        db.create_all()
        user = User(name="Test Landlord", email="test@example.com", role="landlord")
        db.session.add(user)
        db.session.commit()
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={"mfa_verified": False},
        )

    create_app({
        **test_config,
        "JWT_SECRET_KEY": "another-secret-key-that-is-at-least-32-characters",
        "REQUIRE_TWO_FACTOR": True,
    })

    response = first_app.test_client().get(
        "/api/properties",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200


def test_jwt_validation_tolerates_small_clock_skew():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URI,
            "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
            "REQUIRE_TWO_FACTOR": False,
            "JWT_DECODE_LEEWAY": 5,
        }
    )
    with app.app_context():
        assert_isolated_test_database(app)
        db.create_all()
        user = User(name="Clock Test", email="clock@example.com", role="landlord")
        db.session.add(user)
        db.session.commit()
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "mfa_verified": False,
                "iat": int(datetime.now(timezone.utc).timestamp()) + 2,
            },
        )

    response = app.test_client().get(
        "/api/properties",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
