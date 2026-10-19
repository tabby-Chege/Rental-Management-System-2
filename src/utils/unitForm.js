const isNonNegativeNumber = (value) =>
  value !== "" && Number.isFinite(Number(value)) && Number(value) >= 0;

export function formatBedroomCount(bedrooms) {
  if (bedrooms == null) return "Bedroom count not specified";
  if (bedrooms === 0) return "Studio / bedsitter (0 bedrooms)";
  return `${bedrooms} ${bedrooms === 1 ? "bedroom" : "bedrooms"}`;
}

export function formatUnitType(unitType, bedrooms) {
  if (unitType) return unitType.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  if (bedrooms === 0) return "Studio / bedsitter";
  if (Number.isInteger(bedrooms) && bedrooms > 0) {
    return `${bedrooms}-bedroom`;
  }
  return "Unit type not specified";
}

export function validateUnitForm(
  form,
  { requireProperty = true, requireDetails = false } = {}
) {
  const errors = {};

  if (requireProperty) {
    const propertyId = Number(form.property_id);
    if (String(form.property_id).trim() === "" || !Number.isInteger(propertyId) || propertyId < 1) {
      errors.property_id = "Choose a property.";
    }
  }

  if (!String(form.unit_number).trim()) errors.unit_number = "Unit number is required.";

  if (requireDetails && !String(form.unit_type ?? "").trim()) {
    errors.unit_type = "Choose a unit type.";
  }

  if (requireDetails && String(form.bedrooms ?? "").trim() === "") {
    errors.bedrooms = "Enter the number of bedrooms (use 0 for a studio or bedsitter).";
  }
  const bedrooms = String(form.bedrooms ?? "").trim();
  if (bedrooms && (!isNonNegativeNumber(bedrooms) || !Number.isInteger(Number(bedrooms)))) {
    errors.bedrooms = "Bedrooms must be a whole number.";
  }

  if (requireDetails && String(form.bathrooms ?? "").trim() === "") {
    errors.bathrooms = "Enter the number of bathrooms.";
  }
  const bathrooms = String(form.bathrooms ?? "").trim();
  if (bathrooms && !isNonNegativeNumber(bathrooms)) {
    errors.bathrooms = "Bathrooms must be a number, like 1 or 1.5.";
  } else if (bathrooms && Number(bathrooms) > 99.9) {
    errors.bathrooms = "Bathrooms must not exceed 99.9.";
  } else if (bathrooms && Number(bathrooms) !== Number(Number(bathrooms).toFixed(1))) {
    errors.bathrooms = "Bathrooms may have at most one decimal place.";
  }

  const rent = String(form.rent_amount ?? "").trim();
  if (requireDetails && !rent) errors.rent_amount = "Enter the monthly rent in KES.";
  if (rent && (!isNonNegativeNumber(rent) || Number(rent) === 0)) {
    errors.rent_amount = "Monthly rent must be greater than zero.";
  } else if (rent && Number(rent) > 99999999.99) {
    errors.rent_amount = "Monthly rent must not exceed KES 99,999,999.99.";
  } else if (rent && Number(rent) !== Number(Number(rent).toFixed(2))) {
    errors.rent_amount = "Monthly rent may have at most two decimal places.";
  }

  const unitType = String(form.unit_type ?? "").trim();
  if (unitType.length > 50) errors.unit_type = "Unit type must be 50 characters or fewer.";

  const description = String(form.description ?? "");
  if (description.length > 5000) {
    errors.description = "Description must be 5000 characters or fewer.";
  }

  return errors;
}
