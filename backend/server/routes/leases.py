from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from server.extensions import db
from server.models import Lease, Unit, Property

leases_bp = Blueprint('leases_bp', __name__)

@leases_bp.route('/api/leases', methods=['GET'])
@jwt_required()
def get_leases():
    user_id = int(get_jwt_identity())
    tenant_id_query = request.args.get('tenant_id', type=int)

    # Scoped to logged-in user through properties owned by the user
    query = db.session.query(Lease)\
        .join(Unit, Lease.unit_id == Unit.id)\
        .join(Property, Unit.property_id == Property.id)\
        .filter(Property.owner_id == user_id)

    if tenant_id_query:
        query = query.filter(Lease.tenant_id == tenant_id_query)

    leases = query.all()
    return jsonify([lease.to_dict() for lease in leases]), 200


@leases_bp.route('/api/leases', methods=['POST'])
@jwt_required()
def create_lease():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    required_fields = ['unit_id', 'tenant_id', 'start_date', 'end_date', 'monthly_rent', 'deposit']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    # Verify unit belongs to a property owned by current user
    unit = db.session.query(Unit)\
        .join(Property, Unit.property_id == Property.id)\
        .filter(Unit.id == data['unit_id'], Property.owner_id == user_id)\
        .first()

    if not unit:
        return jsonify({"error": "Unit not found or unauthorized"}), 404

    try:
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    new_lease = Lease(
        unit_id=data['unit_id'],
        tenant_id=data['tenant_id'],
        start_date=start_date,
        end_date=end_date,
        monthly_rent=data['monthly_rent'],
        deposit=data['deposit'],
        status=data.get('status', 'active')
    )

    db.session.add(new_lease)
    db.session.commit()

    return jsonify(new_lease.to_dict()), 201


@leases_bp.route('/api/leases/<int:lease_id>', methods=['PATCH', 'DELETE'])
@jwt_required()
def update_lease_status(lease_id):
    user_id = int(get_jwt_identity())

    lease = db.session.query(Lease)\
        .join(Unit, Lease.unit_id == Unit.id)\
        .join(Property, Unit.property_id == Property.id)\
        .filter(Lease.id == lease_id, Property.owner_id == user_id)\
        .first()

    if not lease:
        return jsonify({"error": "Lease not found or unauthorized"}), 404

    if request.method == 'DELETE':
        lease.status = 'terminated'
    elif request.method == 'PATCH':
        data = request.get_json() or {}
        if 'status' in data:
            lease.status = data['status']

    db.session.commit()
    return jsonify(lease.to_dict()), 200