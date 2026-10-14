from datetime import datetime
from server.extensions import db


class Unit(db.Model):
    __tablename__ = 'units'

    id = db.Column(db.Integer, primary_key=True)
    unit_number = db.Column(db.String(50), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    bedrooms = db.Column(db.Integer, nullable=False, default=1)
    bathrooms = db.Column(db.Float, nullable=False, default=1.0)
    rent_amount = db.Column(db.Numeric(10, 2), nullable=False)
    is_occupied = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    leases = db.relationship('Lease', backref='unit', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'unit_number': self.unit_number,
            'property_id': self.property_id,
            'bedrooms': self.bedrooms,
            'bathrooms': self.bathrooms,
            'rent_amount': float(self.rent_amount),
            'is_occupied': self.is_occupied,
            'created_at': self.created_at.isoformat()
        }


class Lease(db.Model):
    __tablename__ = 'leases'

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    monthly_rent = db.Column(db.Numeric(10, 2), nullable=False)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'unit_id': self.unit_id,
            'tenant_id': self.tenant_id,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'monthly_rent': float(self.monthly_rent),
            'deposit_amount': float(self.deposit_amount),
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat()
        }