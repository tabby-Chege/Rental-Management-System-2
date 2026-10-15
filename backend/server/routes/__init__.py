from flask import Flask
from server.extensions import db, jwt

def create_app():
    app = Flask(__name__)
    app.config.from_object('server.config.Config')

    db.init_app(app)
    jwt.init_app(app)

    # Register Blueprints using relative/package imports
    from server.routes.units import units_bp
    from server.routes.leases import leases_bp

    app.register_blueprint(units_bp)
    app.register_blueprint(leases_bp)

    return app