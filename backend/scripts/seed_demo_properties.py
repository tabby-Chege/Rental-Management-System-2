"""Add opt-in sample listings to a local development database."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from server import create_app
from server.extensions import db
from server.models import Property, User
from server.models_unit_lease import Unit
from server.routes.auth import password_validation_error

DEMO_LANDLORD_NAME = "Rental Management Demo Landlord"
SAMPLE_PROPERTIES = [
    {
        "name": "Demo: Kilimani Garden Apartments",
        "address_line": "14 Rose Avenue",
        "city": "Nairobi",
        "region": "Nairobi County",
        "country": "KE",
        "currency": "KES",
        "time_zone": "Africa/Nairobi",
        "unit_number": "A1",
        "unit_type": "two-bedroom",
        "bedrooms": 2,
        "bathrooms": 1.5,
        "rent_amount": 32000,
        "layout": "2+1",
    },
    {
        "name": "Demo: Westlands Courtyard",
        "address_line": "8 Brookside Drive",
        "city": "Nairobi",
        "region": "Nairobi County",
        "country": "KE",
        "currency": "KES",
        "time_zone": "Africa/Nairobi",
        "unit_number": "B2",
        "unit_type": "one-bedroom",
        "bedrooms": 1,
        "bathrooms": 1,
        "rent_amount": 28000,
        "layout": "1+1",
    },
    {
        "name": "Demo: Nyali Seaview Residences",
        "address_line": "22 Links Road",
        "city": "Mombasa",
        "region": "Mombasa County",
        "country": "KE",
        "currency": "KES",
        "time_zone": "Africa/Nairobi",
        "unit_number": "C3",
        "unit_type": "three-bedroom",
        "bedrooms": 3,
        "bathrooms": 2,
        "rent_amount": 54000,
        "layout": "3+1",
    },
    {
        "name": "Demo: Kisumu Lakeside Homes",
        "address_line": "5 Oginga Odinga Road",
        "city": "Kisumu",
        "region": "Kisumu County",
        "country": "KE",
        "currency": "KES",
        "time_zone": "Africa/Nairobi",
        "unit_number": "D4",
        "unit_type": "one-bedroom",
        "bedrooms": 1,
        "bathrooms": 1,
        "rent_amount": 18000,
        "layout": "1+1",
    },
    {
        "name": "Demo: Kampala Acacia Court",
        "address_line": "17 Acacia Avenue",
        "city": "Kampala",
        "region": "Central Region",
        "country": "UG",
        "currency": "UGX",
        "time_zone": "Africa/Kampala",
        "unit_number": "E5",
        "unit_type": "two-bedroom",
        "bedrooms": 2,
        "bathrooms": 2,
        "rent_amount": 950000,
        "layout": "2+1",
    },
    {
        "name": "Demo: Kigali Heights",
        "address_line": "11 KG 7 Avenue",
        "city": "Kigali",
        "region": "Kigali",
        "country": "RW",
        "currency": "RWF",
        "time_zone": "Africa/Kigali",
        "unit_number": "F6",
        "unit_type": "one-bedroom",
        "bedrooms": 1,
        "bathrooms": 1,
        "rent_amount": 480000,
        "layout": "1+1",
    },
    {
        "name": "Demo: Johannesburg Rosebank Flats",
        "address_line": "9 Oxford Road",
        "city": "Johannesburg",
        "region": "Gauteng",
        "country": "ZA",
        "currency": "ZAR",
        "time_zone": "Africa/Johannesburg",
        "unit_number": "G7",
        "unit_type": "two-bedroom",
        "bedrooms": 2,
        "bathrooms": 1,
        "rent_amount": 12500,
        "layout": "2+1",
    },
    {
        "name": "Demo: Cape Town Gardens Cottage",
        "address_line": "3 Kloof Street",
        "city": "Cape Town",
        "region": "Western Cape",
        "country": "ZA",
        "currency": "ZAR",
        "time_zone": "Africa/Johannesburg",
        "unit_number": "H8",
        "unit_type": "studio",
        "bedrooms": 0,
        "bathrooms": 1,
        "rent_amount": 8900,
        "layout": "studio",
    },
    {
        "name": "Demo: London Market Mews",
        "address_line": "12 Market Street",
        "city": "London",
        "region": "England",
        "country": "GB",
        "currency": "GBP",
        "time_zone": "Europe/London",
        "unit_number": "J9",
        "unit_type": "one-bedroom",
        "bedrooms": 1,
        "bathrooms": 1,
        "rent_amount": 1650,
        "layout": "1+1",
    },
    {
        "name": "Demo: Toronto Maple House",
        "address_line": "27 Queen Street West",
        "city": "Toronto",
        "region": "Ontario",
        "country": "CA",
        "currency": "CAD",
        "time_zone": "America/Toronto",
        "unit_number": "K10",
        "unit_type": "two-bedroom",
        "bedrooms": 2,
        "bathrooms": 1,
        "rent_amount": 2450,
        "layout": "2+1",
    },
    {
        "name": "Demo: Lisbon Sunlight Apartments",
        "address_line": "6 Rua do Sol",
        "city": "Lisbon",
        "region": "Lisbon",
        "country": "PT",
        "currency": "EUR",
        "time_zone": "Europe/Lisbon",
        "unit_number": "L11",
        "unit_type": "two-bedroom",
        "bedrooms": 2,
        "bathrooms": 1,
        "rent_amount": 1400,
        "layout": "2+1",
    },
    {
        "name": "Demo: Accra Palm Grove",
        "address_line": "19 Cantonments Road",
        "city": "Accra",
        "region": "Greater Accra",
        "country": "GH",
        "currency": "GHS",
        "time_zone": "Africa/Accra",
        "unit_number": "M12",
        "unit_type": "three-bedroom",
        "bedrooms": 3,
        "bathrooms": 2,
        "rent_amount": 4200,
        "layout": "3+1",
    },
]


def require_local_development_target():
    if os.getenv("APP_ENV", "").lower() != "development":
        raise SystemExit("Set APP_ENV=development before seeding sample listings.")
    if os.getenv("ENABLE_DEMO_DATA", "").lower() != "true":
        raise SystemExit("Set ENABLE_DEMO_DATA=true to opt in to sample listings.")

    raw_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if not raw_url:
        raise SystemExit("Set DATABASE_URL to a local development database.")
    url = make_url(raw_url)
    if url.drivername.startswith("sqlite"):
        if not url.database or url.database == ":memory:":
            raise SystemExit("Sample listings require a persistent local database.")
        return

    database_name = (url.database or "").lower()
    if (
        url.host not in {"localhost", "127.0.0.1", "::1"}
        or not any(marker in database_name for marker in ("dev", "demo", "test"))
    ):
        raise SystemExit(
            "Refusing to seed a remote or non-development database. "
            "Use SQLite or a localhost database named with dev, demo, or test."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-development-data",
        action="store_true",
        help="confirm that the configured database is a local development database",
    )
    args = parser.parse_args()
    require_local_development_target()
    if not args.confirm_development_data:
        parser.error("pass --confirm-development-data to add demo records")

    landlord_email = os.getenv(
        "DEMO_LANDLORD_EMAIL", "demo-landlord@example.test"
    ).strip().lower()
    landlord_password = os.getenv("DEMO_LANDLORD_PASSWORD", "")
    if not landlord_email or "@" not in landlord_email:
        raise SystemExit("DEMO_LANDLORD_EMAIL must be a valid email address.")
    password_error = password_validation_error(landlord_password)
    if password_error:
        raise SystemExit(
            f"Set DEMO_LANDLORD_PASSWORD to a strong development-only password. "
            f"{password_error}."
        )

    app = create_app()
    with app.app_context():
        landlord = User.query.filter_by(email=landlord_email).first()
        if landlord and (
            landlord.role != "landlord" or landlord.name != DEMO_LANDLORD_NAME
        ):
            raise SystemExit(
                "The configured demo email already belongs to a different account; "
                "no records were changed."
            )
        if not landlord:
            landlord = User(
                name=DEMO_LANDLORD_NAME,
                email=landlord_email,
                role="landlord",
            )
            landlord.set_password(landlord_password)
            db.session.add(landlord)
            db.session.flush()

        created = 0
        for sample in SAMPLE_PROPERTIES:
            property_name = sample["name"]
            if Property.query.filter_by(
                owner_id=landlord.id, name=property_name
            ).first():
                continue
            unit_values = {
                key: sample[key]
                for key in (
                    "unit_number",
                    "unit_type",
                    "bedrooms",
                    "bathrooms",
                    "rent_amount",
                    "layout",
                )
            }
            property_values = {
                key: sample[key]
                for key in (
                    "address_line",
                    "city",
                    "region",
                    "country",
                    "currency",
                    "time_zone",
                )
            }
            property_record = Property(
                owner_id=landlord.id,
                name=property_name,
                rental_type="multi_unit",
                subtype="apartment_block",
                floors=1,
                description=(
                    "Fictional demo listing for local development and evaluation only."
                ),
                **property_values,
            )
            db.session.add(property_record)
            db.session.flush()
            db.session.add(Unit(property_id=property_record.id, **unit_values))
            created += 1

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise SystemExit(
                "Could not add all demo listings because of a database conflict; "
                "the transaction was rolled back."
            )

        print(
            f"Demo landlord: {landlord_email}; "
            f"created {created} sample properties; "
            f"{len(SAMPLE_PROPERTIES) - created} already existed."
        )


if __name__ == "__main__":
    main()
