import pytest

from server import create_app


def test_app_requires_database_and_long_jwt_secret(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app()

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        create_app()


def test_cors_only_allows_configured_frontend_origin():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
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

    assert allowed.headers["Access-Control-Allow-Origin"] == "https://rentals.example"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_http_errors_use_json_error_shape():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
        }
    )

    response = app.test_client().get("/missing")

    assert response.status_code == 404
    assert set(response.get_json()) == {"error"}
