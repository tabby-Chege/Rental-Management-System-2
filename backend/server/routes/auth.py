from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
)

from server.decorators import role_required
from server.extensions import db
from server.models import User


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not name or not email or not password:
        return {
            "error": "Name, email, and password are required"
        }, 400

    if "@" not in email or "." not in email.split("@")[-1]:
        return {
            "error": "Please provide a valid email address"
        }, 400

    if len(password) < 8:
        return {
            "error": "Password must be at least 8 characters long"
        }, 400

    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        return {
            "error": "A user with this email already exists"
        }, 409

    user = User(
        name=name,
        email=email,
    )

    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))

    return {
        "message": "User registered successfully",
        "user": user.to_dict(),
        "access_token": access_token,
    }, 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return {
            "error": "Email and password are required"
        }, 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return {
            "error": "Invalid email or password"
        }, 401

    access_token = create_access_token(identity=str(user.id))

    return {
        "message": "Login successful",
        "user": user.to_dict(),
        "access_token": access_token,
    }, 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    user_id = get_jwt_identity()

    user = User.query.get(user_id)

    if not user:
        return {
            "error": "User not found"
        }, 404

    return {
        "user": user.to_dict()
    }, 200


@auth_bp.route("/admin-test", methods=["GET"])
@role_required("admin")
def admin_test():
    return {
        "message": "You have admin access"
    }, 200
