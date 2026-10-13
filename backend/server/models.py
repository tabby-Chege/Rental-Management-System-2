from datetime import datetime, timezone
from server.extensions import db  # Use shared db instance from server.extensions


class Unit(db.Model):
    __tablename__ = 'units'

    id = db.Column(db.Integer, primary_key=True)
    unit_number = db.Column(db.String(50), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    bedrooms = db.Column(db.Integer, nullable=False, default=1)
    bathrooms = db.Column(db.Float, nullable=False, default=1.0)
    rent_amount = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )

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
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Lease(db.Model):
    __tablename__ = 'leases'

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    monthly_rent = db.Column(db.Numeric(10, 2), nullable=False)
    deposit = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    status = db.Column(db.String(20), nullable=False, default='active')  # 'active', 'terminated', etc.
    created_at = db.Column(
        db.DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        return {
            'id': self.id,
            'unit_id': self.unit_id,
            'tenant_id': self.tenant_id,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'monthly_rent': float(self.monthly_rent),
            'deposit': float(self.deposit),
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }