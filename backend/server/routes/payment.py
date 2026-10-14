from flask import Blueprint, jsonify, request
from server.models import db, Payment

payments_bp = Blueprint('payments_bp', __name__)

@payments_bp.route('/payments', methods=['GET'])
def get_payments():
    payments = Payment.query.all()
    return jsonify([p.to_dict() for p in payments]), 200

@payments_bp.route('/payments', methods=['POST'])
def create_payment():
    data = request.get_json()
    
    new_payment = Payment(
        lease_id=data.get('lease_id'),
        amount=data.get('amount'),
        payment_method=data.get('payment_method'),
        status=data.get('status', 'Completed'),
        reference_code=data.get('reference_code')
    )
    
    db.session.add(new_payment)
    db.session.commit()
    
    return jsonify(new_payment.to_dict()), 201