from flask import Flask
from flask_cors import CORS

from server.config import Config
from server.extensions import bcrypt, db, jwt
from server.routes.auth import auth_bp
<<<<<<< HEAD
from server.routes.payment import payments_bp
=======
from server.routes.properties import properties_bp

>>>>>>> origin/sonia-properties

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)

    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    app.register_blueprint(auth_bp)
<<<<<<< HEAD
    app.register_blueprint(payments_bp)
=======
    app.register_blueprint(properties_bp)

>>>>>>> origin/sonia-properties
    @app.route("/api/health")
    def health():
        return {"message": "Rental Management API is running"}

    with app.app_context():
        db.create_all()

    return app
