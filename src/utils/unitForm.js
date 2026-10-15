const isNonNegativeNumber = (value) => value !== "" && !Number.isNaN(Number(value)) && Number(value) >= 0;

export function validateUnitForm(form, { requireProperty = true } = {}) {
  const errors = {};

  if (requireProperty) {
    const propertyId = Number(form.property_id);
    if (String(form.property_id).trim() === "" || !Number.isInteger(propertyId) || propertyId < 1) {
      errors.property_id = "Choose a property.";
    }
  }

  if (!String(form.unit_number).trim()) errors.unit_number = "Unit number is required.";

  const bedrooms = String(form.bedrooms ?? "").trim();
  if (bedrooms && (!isNonNegativeNumber(bedrooms) || !Number.isInteger(Number(bedrooms)))) {
    errors.bedrooms = "Bedrooms must be a whole number.";
  }

  const bathrooms = String(form.bathrooms ?? "").trim();
  if (bathrooms && !isNonNegativeNumber(bathrooms)) {
    errors.bathrooms = "Bathrooms must be a number, like 1 or 1.5.";
  }

  const rent = String(form.rent_amount ?? "").trim();
  if (rent && !isNonNegativeNumber(rent)) errors.rent_amount = "Rent must be a positive number.";

  return errors;
}
