"""Ownership rules: user -> property -> unit -> lease.

Property access comes from Sonia's helpers in routes/properties.py, so units and
leases follow exactly the same rules as properties: landlords see only their
own records, admins see everything.
"""
from sqlalchemy import select

from server.extensions import db
from server.models import Property
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit
from server.routes.properties import get_accessible_property, owned_properties_query


def get_owned_property(user, property_id):
    return get_accessible_property(property_id, user)


def _accessible_property_ids(user):
    """SELECT id of every property this user may access (Sonia's rule)."""
    return select(owned_properties_query(user).with_entities(Property.id).subquery().c.id)


def owned_units_query(user):
    return Unit.query.filter(Unit.property_id.in_(_accessible_property_ids(user)))


def get_owned_unit(user, unit_id):
    return owned_units_query(user).filter(Unit.id == unit_id).first()


def owned_leases_query(user):
    return Lease.query.join(Unit, Lease.unit_id == Unit.id).filter(
        Unit.property_id.in_(_accessible_property_ids(user))
    )


def get_owned_lease(user, lease_id):
    return owned_leases_query(user).filter(Lease.id == lease_id).first()


def get_tenant_for_unit(unit, tenant_id):
    """A lease may only use a tenant created by the landlord who owns the unit's property.

    Tenants belong to a landlord (Tenant.landlord_id), so the check is against the
    property's owner. For a normal landlord that is just themselves.
    """
    owner_id = db.session.get(Property, unit.property_id).owner_id
    return Tenant.query.filter_by(id=tenant_id, landlord_id=owner_id).first()
