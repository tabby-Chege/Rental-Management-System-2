from datetime import datetime, timezone

from server.extensions import bcrypt, db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="tenant")
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


class Property(db.Model):
    __tablename__ = "properties"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    zip_code = db.Column(db.String(20))
    description = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }


class Unit(db.Model):
    __tablename__ = "units"

    id = db.Column(db.Integer, primary_key=True)
    unit_number = db.Column(db.String(50), nullable=False)
    property_id = db.Column(
        db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True
    )
    bedrooms = db.Column(db.Integer, nullable=False, default=1)
    bathrooms = db.Column(db.Float, nullable=False, default=1.0)
    rent_amount = db.Column(db.Numeric(10, 2), nullable=False)
    is_occupied = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    leases = db.relationship(
        "Lease", backref="unit", cascade="all, delete-orphan", lazy=True
    )

    def to_dict(self):
        return {
            "id": self.id,
            "unit_number": self.unit_number,
            "property_id": self.property_id,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "rent_amount": float(self.rent_amount),
            "is_occupied": self.is_occupied,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Lease(db.Model):
    __tablename__ = "leases"

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    monthly_rent = db.Column(db.Numeric(10, 2), nullable=False)
    deposit = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "tenant_id": self.tenant_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "monthly_rent": float(self.monthly_rent),
            "deposit": float(self.deposit),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
