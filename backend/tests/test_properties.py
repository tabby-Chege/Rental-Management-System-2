from server import create_app
from server.extensions import db
from server.models import User


def test_health_endpoint():
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["message"] == "Rental Management API is running"


def test_properties_require_authentication():
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.get("/api/properties")

    assert response.status_code == 401
