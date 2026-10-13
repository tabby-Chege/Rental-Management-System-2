from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models_unit_lease import db, Lease, Unit

leases_bp = Blueprint('leases_bp', __name__)

@leases_bp.route('/leases', methods=['POST'])
@jwt_required()
def create_lease():
    data = request.get_json()
    
    required_fields = ['unit_id', 'tenant_id', 'start_date', 'end_date', 'monthly_rent', 'deposit_amount']
    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required lease fields"}), 400

    unit_id = data['unit_id']
    unit = Unit.query.get(unit_id)
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

   
    try:
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if start_date >= end_date:
        return jsonify({"error": "End date must occur after start date"}), 400

    overlapping_lease = Lease.query.filter(
        Lease.unit_id == unit_id,
        Lease.is_active == True,
        Lease.start_date <= end_date,
        Lease.end_date >= start_date
    ).first()

    if overlapping_lease:
        return jsonify({"error": "Conflict: Unit is already leased during this timeframe."}), 409

    new_lease = Lease(
        unit_id=unit_id,
        tenant_id=data['tenant_id'],
        start_date=start_date,
        end_date=end_date,
        monthly_rent=data['monthly_rent'],
        deposit_amount=data['deposit_amount'],
        is_active=True
    )


    unit.is_occupied = True

    db.session.add(new_lease)
    db.session.commit()

    return jsonify(new_lease.to_dict()), 201


@leases_bp.route('/leases/<int:lease_id>', methods=['DELETE'])
@jwt_required()
def terminate_lease(lease_id):
    lease = Lease.query.get(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    lease.is_active = False
    
    unit = Unit.query.get(lease.unit_id)
    if unit:
        unit.is_occupied = False

    db.session.commit()

    return jsonify({"message": "Lease terminated successfully"}), 200