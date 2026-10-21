import { currencyPrecision } from "./money.js";

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
  {
    requireProperty = true,
    requireDetails = false,
    requireUnitNumber = true,
    requireUnitType = true,
    currency,
    floors,
  } = {}
) {
  const errors = {};

  if (requireProperty) {
    const propertyId = Number(form.property_id);
    if (String(form.property_id).trim() === "" || !Number.isInteger(propertyId) || propertyId < 1) {
      errors.property_id = "Choose a property.";
    }
  }

  if (requireUnitNumber && !String(form.unit_number ?? "").trim()) {
    errors.unit_number = "Unit number is required.";
  }

  if (requireDetails && requireUnitType && !String(form.unit_type ?? "").trim()) {
    errors.unit_type = "Choose a unit type.";
  }

  if (requireDetails && String(form.bedrooms ?? "").trim() === "") {
    errors.bedrooms = "Enter the number of bedrooms (use 0 for a studio or bedsitter).";
  }
  const bedrooms = String(form.bedrooms ?? "").trim();
  if (bedrooms && (!isNonNegativeNumber(bedrooms) || !Number.isInteger(Number(bedrooms)))) {
    errors.bedrooms = "Bedrooms must be a whole number.";
  }
  const layout = String(form.layout ?? "").trim();
  if (layout && layout !== "studio" && !/^\d{1,2}\+\d{1,2}$/.test(layout)) {
    errors.layout = "Use a layout like 2+1, or choose studio.";
  } else if (layout === "studio" && bedrooms && Number(bedrooms) !== 0) {
    errors.layout = "A studio layout must have 0 bedrooms.";
  } else if (layout && /^\d{1,2}\+\d{1,2}$/.test(layout) && bedrooms
    && Number(layout.split("+")[0]) !== Number(bedrooms)) {
    errors.layout = "Bedrooms must match the bedroom count in the layout.";
  }

  const floor = String(form.floor_number ?? "").trim();
  if (floor && (!/^\d+$/.test(floor) || Number(floor) < 1)) {
    errors.floor_number = "Floor must be a whole number of at least 1.";
  } else if (floor && floors && Number(floor) > Number(floors)) {
    errors.floor_number = "Floor cannot exceed the property's number of floors.";
  }

  const size = String(form.size ?? "").trim();
  if (size && (!isNonNegativeNumber(size) || Number(size) === 0
    || Number(size) !== Number(Number(size).toFixed(2)))) {
    errors.size = "Size must be a positive number with at most two decimal places.";
  }
  if (size && !form.size_unit) errors.size_unit = "Choose a size unit.";
  if (!size && form.size_unit) errors.size_unit = "Enter a size or clear the size unit.";

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
  const precision = currencyPrecision(currency);
  if (requireDetails && !rent) errors.rent_amount = "Enter the monthly rent.";
  if (rent && (!isNonNegativeNumber(rent) || Number(rent) === 0)) {
    errors.rent_amount = "Monthly rent must be greater than zero.";
  } else if (rent && Number(rent) >= 1000000000) {
    errors.rent_amount = "Monthly rent is too large.";
  } else if (rent && Number(rent) !== Number(Number(rent).toFixed(precision))) {
    errors.rent_amount = `Monthly rent may have at most ${precision} decimal places for ${currency}.`;
  }

  const unitType = String(form.unit_type ?? "").trim();
  if (unitType.length > 50) errors.unit_type = "Unit type must be 50 characters or fewer.";

  const description = String(form.description ?? "");
  if (description.length > 5000) {
    errors.description = "Description must be 5000 characters or fewer.";
  }

  return errors;
}
