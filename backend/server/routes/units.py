from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models_unit_lease import db, Unit
from models_property import Property

units_bp = Blueprint('units_bp', __name__)

@units_bp.route('/properties/<int:property_id>/units', methods=['GET'])
@jwt_required()
def get_property_units(property_id):
    user_id = int(get_jwt_identity())
    property_item = Property.query.filter_by(id=property_id, user_id=user_id).first()
    
    if not property_item:
        return jsonify({"error": "Property not found or unauthorized"}), 404

    units = Unit.query.filter_by(property_id=property_id).all()
    return jsonify([unit.to_dict() for unit in units]), 200


@units_bp.route('/properties/<int:property_id>/units', methods=['POST'])
@jwt_required()
def create_unit(property_id):
    user_id = int(get_jwt_identity())
    property_item = Property.query.filter_by(id=property_id, user_id=user_id).first()
    
    if not property_item:
        return jsonify({"error": "Property not found or unauthorized"}), 404

    data = request.get_json()
    if not data or not data.get('unit_number') or not data.get('rent_amount'):
        return jsonify({"error": "Missing required fields (unit_number, rent_amount)"}), 400

    new_unit = Unit(
        unit_number=data['unit_number'],
        property_id=property_id,
        bedrooms=data.get('bedrooms', 1),
        bathrooms=data.get('bathrooms', 1.0),
        rent_amount=data['rent_amount'],
        is_occupied=False
    )

    db.session.add(new_unit)
    db.session.commit()

    return jsonify(new_unit.to_dict()), 201