from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from pathlib import Path
from werkzeug.exceptions import HTTPException

from server.routes.tenants import tenants_bp
from server.config import Config
from server.extensions import bcrypt, db, jwt, migrate
from server.routes.auth import auth_bp
from server.routes.payment import payments_bp
from server.routes.properties import properties_bp
from server.routes.units import units_bp
from server.routes.leases import leases_bp
from server.models import Property, RevokedToken, User
from server.models_application import Application, ReservationNotification
from server.models_communications import PropertyConversation, PropertyMessage
from server.models_media import ListingReport, PropertyPhoto
from server.models_landlord_tools import LeaseDocument, MaintenancePhoto, MaintenanceRequest
from server.models_auth_factors import (
    AuthOtpChallenge,
    AuthPasskeyChallenge,
    PasskeyCredential,
    RecoveryCode,
)
from server.models_payment import (
    DepositLedgerEntry,
    EmailOutbox,
    PaymentAllocation,
    PaymentAttempt,
    RentInvoice,
    RentSchedule,
)
from server.models_tenant import Tenant, TenantDocument, TenantProfile
from server.models_unit_lease import Lease, Room, Unit
from server.routes.applications import applications_bp
from server.routes.tenant_profiles import tenant_profiles_bp
from server.routes.notifications import notifications_bp
from server.routes.payment_gateway import payment_gateway_bp
from server.routes.media import media_bp
from server.routes.communications import communications_bp
from server.routes.landlord_tools import landlord_tools_bp
from server.reservations import process_reservations
from server.payment_service import (
    process_email_outbox,
    process_pending_payment_attempts,
    process_rent_schedules,
)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(Config.load())
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("Set DATABASE_URL or SQLALCHEMY_DATABASE_URI before starting the API")
    jwt_secret = app.config.get("JWT_SECRET_KEY")
    if not isinstance(jwt_secret, str) or len(jwt_secret) < 32:
        raise RuntimeError("Set JWT_SECRET_KEY to a random secret of at least 32 characters")
    if not app.config.get("CORS_ORIGINS"):
        raise RuntimeError("Set CORS_ORIGINS to the trusted frontend origin or origins")
    if app.config.get("PAYMENT_ENVIRONMENT") not in {"sandbox", "live"}:
        raise RuntimeError("PAYMENT_ENVIRONMENT must be sandbox or live")

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config["CORS_ORIGINS"],
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                "allow_headers": ["Authorization", "Content-Type"],
            }
        },
    )

    db.init_app(app)
    migration_directory = Path(__file__).resolve().parent.parent / "migrations" / "alembic"
    migrate.init_app(app, db, directory=str(migration_directory))
    bcrypt.init_app(app)
    jwt.init_app(app)

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        message = "Your session has ended. Please sign in again to continue."
        return jsonify({"error": message, "msg": message}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({"error": "Invalid authentication token"}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({"error": "Authentication token is required"}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({"error": "Authentication token has been revoked"}), 401

    @jwt.token_in_blocklist_loader
    def token_in_blocklist(jwt_header, jwt_payload):
        if db.session.get(RevokedToken, jwt_payload["jti"]) is not None:
            return True
        if app.config.get("REQUIRE_TWO_FACTOR"):
            if jwt_payload.get("mfa_verified") is not True:
                return True
            user = db.session.get(User, jwt_payload.get("sub"))
            return user is None or not user.totp_enabled
        return False

    @jwt.needs_fresh_token_loader
    def fresh_token_callback(jwt_header, jwt_payload):
        return jsonify({"error": "A fresh authentication token is required"}), 401

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"error": error.description}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unhandled API error")
        return jsonify({"error": "An unexpected server error occurred"}), 500

    app.register_blueprint(auth_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(properties_bp)
    app.register_blueprint(units_bp)
    app.register_blueprint(leases_bp)
    app.register_blueprint(tenants_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(tenant_profiles_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(payment_gateway_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(communications_bp)
    app.register_blueprint(landlord_tools_bp)

    @app.cli.command("process-reservations")
    def process_reservations_command():
        result = process_reservations()
        app.logger.info("Reservation processing completed: %s", result)
        print(result)

    @app.cli.command("process-payment-attempts")
    def process_payment_attempts_command():
        result = process_pending_payment_attempts()
        app.logger.info("Payment attempt checks completed: %s", result)
        print(result)

    @app.cli.command("process-rent-schedules")
    def process_rent_schedules_command():
        result = process_rent_schedules()
        app.logger.info("Rent schedule processing completed: %s", result)
        print(result)

    @app.cli.command("process-email-outbox")
    def process_email_outbox_command():
        result = process_email_outbox()
        app.logger.info("Email outbox processing completed: %s", result)
        print(result)

    @app.route("/api/health")
    def health():
        return {"message": "Rental Management API is running"}

    return app
