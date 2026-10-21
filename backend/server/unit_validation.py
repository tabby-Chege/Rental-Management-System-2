import math
import re
from decimal import Decimal, InvalidOperation

from server.money import parse_money

UNIT_FIELDS = {
    "unit_number",
    "unit_type",
    "bedrooms",
    "bathrooms",
    "rent_amount",
    "floor_number",
    "layout",
    "size",
    "size_unit",
    "furnished",
    "description",
}

SIZE_UNITS = {"sqm", "sqft"}
LAYOUT_PATTERN = re.compile(r"^(\d{1,2})\+(\d{1,2})$")


def validate_unit_data(data, *, currency, floors, partial=False, defaults=None):
    if not isinstance(data, dict) or (partial and not data):
        return None, "Request body must be a JSON object with unit fields"

    unknown = set(data) - UNIT_FIELDS
    if unknown:
        return None, "Unsupported fields: " + ", ".join(sorted(unknown))

    cleaned = dict(defaults or {})
    if "unit_number" in data:
        value = data["unit_number"]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 50:
            return None, "unit_number must be non-empty text of at most 50 characters"
        cleaned["unit_number"] = value.strip()
    elif not partial and "unit_number" not in cleaned:
        return None, "unit_number is required"

    if "unit_type" in data:
        value = data["unit_type"]
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value.strip()) > 50
        ):
            return None, "unit_type must be non-empty text of at most 50 characters or null"
        cleaned["unit_type"] = value.strip() if value else None

    if "description" in data:
        value = data["description"]
        if value is not None and (not isinstance(value, str) or len(value) > 5000):
            return None, "description must be text of at most 5000 characters or null"
        cleaned["description"] = value.strip() if value else None

    for field in ("bedrooms", "floor_number"):
        if field not in data:
            if not partial:
                if field == "floor_number":
                    cleaned.setdefault(field, 1)
            continue
        value = data[field]
        minimum = 0 if field == "bedrooms" else 1
        if field == "bedrooms" and value is None:
            cleaned[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            return None, f"{field} must be a whole number of at least {minimum}"
        if field == "floor_number" and value > floors:
            return None, "floor_number cannot exceed the property's number of floors"
        cleaned[field] = value

    for field in ("bathrooms", "rent_amount", "size"):
        if field not in data:
            if not partial:
                cleaned.setdefault(field, None)
            continue
        value = data[field]
        if value is None:
            if field == "bathrooms" or field == "size":
                cleaned[field] = None
                continue
            cleaned[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"{field} must be a number or null"
        if not math.isfinite(value) or value < 0:
            return None, f"{field} must be a non-negative finite number or null"
        if field == "bathrooms":
            if value > 99.9:
                return None, "bathrooms must not exceed 99.9"
            if round(value, 1) != value:
                return None, "bathrooms must have at most one decimal place"
            cleaned[field] = value
        elif field == "rent_amount":
            amount, error = parse_money(value, currency)
            if error:
                return None, f"rent_amount: {error.lower()}"
            cleaned[field] = amount
        else:
            try:
                size = Decimal(str(value))
                if size <= 0 or size != size.quantize(Decimal("0.01")):
                    raise InvalidOperation
            except InvalidOperation:
                return None, "size must be a positive number with at most two decimal places"
            if size >= Decimal("1000000000"):
                return None, "size is too large"
            cleaned[field] = size

    if "layout" in data:
        value = data["layout"]
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value.strip()) > 20
        ):
            return None, "layout must be text of at most 20 characters or null"
        layout = value.strip().lower() if value else None
        layout_match = LAYOUT_PATTERN.fullmatch(layout or "")
        if layout and layout != "studio" and not layout_match:
            return None, "layout must be studio or use the bedrooms+living-rooms format, such as 2+1"
        if layout_match:
            layout_bedrooms = int(layout_match.group(1))
            if "bedrooms" in data and cleaned.get("bedrooms") != layout_bedrooms:
                return None, "bedrooms must match the bedroom count in layout"
            cleaned["bedrooms"] = layout_bedrooms
        elif layout == "studio":
            if "bedrooms" in data and cleaned.get("bedrooms") != 0:
                return None, "bedrooms must be 0 for a studio layout"
            cleaned["bedrooms"] = 0
        cleaned["layout"] = layout

    effective_layout = cleaned.get("layout")
    effective_bedrooms = cleaned.get("bedrooms")
    layout_match = LAYOUT_PATTERN.fullmatch(effective_layout or "")
    if layout_match and effective_bedrooms is not None:
        if effective_bedrooms != int(layout_match.group(1)):
            return None, "bedrooms must match the bedroom count in layout"
    elif effective_layout == "studio" and effective_bedrooms not in (None, 0):
        return None, "bedrooms must be 0 for a studio layout"

    if "size_unit" in data:
        value = data["size_unit"]
        if value is not None and (
            not isinstance(value, str) or value not in SIZE_UNITS
        ):
            return None, "size_unit must be sqm or sqft"
        cleaned["size_unit"] = value
    if "size" in data and cleaned.get("size") is not None and not (
        data.get("size_unit", cleaned.get("size_unit"))
    ):
        return None, "size_unit is required when size is provided"
    if "size_unit" in data and data["size_unit"] is None and cleaned.get("size") is not None:
        return None, "size_unit cannot be cleared while size is set"

    if "furnished" in data:
        if not isinstance(data["furnished"], bool):
            return None, "furnished must be true or false"
        cleaned["furnished"] = data["furnished"]
    elif not partial:
        cleaned.setdefault("furnished", False)

    effective_floor = cleaned.get("floor_number")
    if effective_floor is not None and effective_floor > floors:
        return None, "floor_number cannot exceed the property's number of floors"

    return cleaned, None
