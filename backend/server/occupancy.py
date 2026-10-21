from datetime import date

from server.extensions import db
from server.models_application import Application, RESERVED_APPLICATION_STATUSES
from server.models_unit_lease import Lease, Unit
from server.reservations import process_reservations


def unit_occupancy(unit_ids, today=None):
    unit_ids = list(unit_ids)
    if not unit_ids:
        return {}

    process_reservations(unit_ids=unit_ids)
    today = today or date.today()
    leases = Lease.query.filter(
        Lease.unit_id.in_(unit_ids),
        Lease.status == "active",
        Lease.start_date <= today,
        Lease.end_date >= today,
    ).all()
    active_leases = {lease.unit_id: lease for lease in leases}
    reserved_unit_ids = {
        unit_id
        for (unit_id,) in db.session.query(Application.unit_id)
        .filter(
            Application.unit_id.in_(unit_ids),
            Application.status.in_(RESERVED_APPLICATION_STATUSES),
        )
        .distinct()
        .all()
    }

    return {
        unit_id: {
            "lease": active_leases.get(unit_id),
            "is_reserved": (
                unit_id not in active_leases and unit_id in reserved_unit_ids
            ),
        }
        for unit_id in unit_ids
    }


def property_occupancy(properties, today=None):
    property_ids = [prop.id for prop in properties]
    summaries = {
        property_id: {
            "total_units": 0,
            "occupied_units": 0,
            "reserved_units": 0,
            "vacant_units": 0,
        }
        for property_id in property_ids
    }
    if not property_ids:
        return summaries

    units = (
        db.session.query(Unit.id, Unit.property_id)
        .filter(Unit.property_id.in_(property_ids))
        .all()
    )
    statuses = unit_occupancy((unit_id for unit_id, _ in units), today=today)
    for unit_id, property_id in units:
        summary = summaries[property_id]
        summary["total_units"] += 1
        status = statuses[unit_id]
        if status["lease"] is not None:
            summary["occupied_units"] += 1
        elif status["is_reserved"]:
            summary["reserved_units"] += 1
        else:
            summary["vacant_units"] += 1
    return summaries


def property_json(prop, summary=None):
    payload = prop.to_dict()
    if summary is not None:
        payload["occupancy_summary"] = summary
    return payload
