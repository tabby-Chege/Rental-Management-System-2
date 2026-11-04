from server.extensions import db


TEST_DATABASE_URI = "sqlite:///:memory:"


def assert_isolated_test_database(app):
    if not app.testing:
        raise RuntimeError("Destructive test fixture operation requires TESTING=True")

    configured_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    if configured_uri != TEST_DATABASE_URI:
        raise RuntimeError(
            "Destructive test fixture operation requires the explicit in-memory "
            "SQLite test database"
        )
    if app.config.get("SQLALCHEMY_BINDS"):
        raise RuntimeError("Destructive test fixture operation does not allow database binds")

    engine_url = db.engine.url
    if (
        engine_url.drivername != "sqlite"
        or engine_url.database != ":memory:"
        or engine_url.query
    ):
        raise RuntimeError(
            "The effective SQLAlchemy engine is not isolated in-memory SQLite"
        )
