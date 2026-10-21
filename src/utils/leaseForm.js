import { currencyPrecision } from "./money.js";

const isNonNegativeNumber = (value) => value !== "" && !Number.isNaN(Number(value)) && Number(value) >= 0;

export function validateLeaseForm(form, { requireUnit = true, currency } = {}) {
  const errors = {};
  const precision = currencyPrecision(currency);

  if (requireUnit && !form.unit_id) errors.unit_id = "Choose a unit.";
  if (!form.tenant_id) errors.tenant_id = "Choose a tenant.";

  if (!form.start_date) errors.start_date = "Start date is required.";
  if (!form.end_date) {
    errors.end_date = "End date is required.";
  } else if (form.start_date && form.end_date < form.start_date) {
    // YYYY-MM-DD strings compare correctly as text.
    errors.end_date = "End date cannot be before the start date.";
  }

  if (!isNonNegativeNumber(String(form.monthly_rent).trim())) {
    errors.monthly_rent = "Enter the monthly rent as a positive number.";
  } else if (Number(form.monthly_rent) <= 0) {
    errors.monthly_rent = "Monthly rent must be greater than zero.";
  } else if (Number(form.monthly_rent) !== Number(Number(form.monthly_rent).toFixed(precision))) {
    errors.monthly_rent = `Monthly rent may have at most ${precision} decimal places for ${currency}.`;
  }

  const deposit = String(form.deposit ?? "").trim();
  if (deposit && !isNonNegativeNumber(deposit)) errors.deposit = "Deposit must be a positive number.";
  else if (deposit && Number(deposit) !== Number(Number(deposit).toFixed(precision))) {
    errors.deposit = `Deposit may have at most ${precision} decimal places for ${currency}.`;
  }

  return errors;
}
