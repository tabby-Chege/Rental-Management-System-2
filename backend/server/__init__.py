from flask import Flask, jsonify
from flask_cors import CORS

from server.routes.tenants import tenants_bp
from server.config import Config
from server.extensions import bcrypt, db, jwt
from server.routes.auth import auth_bp
from server.routes.payment import payments_bp
from server.routes.properties import properties_bp
from server.routes.units import units_bp
from server.routes.leases import leases_bp
from server.models import User, Property
from server.models_application import Application
from server.models_tenant import Tenant
from server.models_unit_lease import Unit, Lease
from server.routes.applications import applications_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)

    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        message = "Your session has ended. Please sign in again to continue."
        return jsonify({"error": message, "msg": message}), 401

    app.register_blueprint(auth_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(properties_bp)
    app.register_blueprint(units_bp)
    app.register_blueprint(leases_bp)
    app.register_blueprint(tenants_bp)
    app.register_blueprint(applications_bp)

    @app.route("/api/health")
    def health():
        return {"message": "Rental Management API is running"}

    with app.app_context():
        db.create_all()

    return app
