import assert from "node:assert/strict";
import test from "node:test";

import { formatBedroomCount, formatUnitType, validateUnitForm } from "./unitForm.js";

test("bedroom validation accepts zero and rejects fractions and negatives", () => {
  const validUnit = {
    property_id: "1",
    unit_number: "S0",
    bedrooms: "0",
  };
  assert.deepEqual(validateUnitForm(validUnit), {});

  assert.equal(
    validateUnitForm({ ...validUnit, bedrooms: "1.5" }).bedrooms,
    "Bedrooms must be a whole number."
  );
  assert.equal(
    validateUnitForm({ ...validUnit, bedrooms: "-1" }).bedrooms,
    "Bedrooms must be a whole number."
  );
});

test("bedroom labels identify studios/bedsitters and singular counts", () => {
  assert.equal(formatBedroomCount(0), "Studio / bedsitter (0 bedrooms)");
  assert.equal(formatBedroomCount(1), "1 bedroom");
  assert.equal(formatBedroomCount(2), "2 bedrooms");
  assert.equal(formatBedroomCount(null), "Bedroom count not specified");
});

test("unit form requires rental details and validates rent and bathroom precision", () => {
  const validUnit = {
    property_id: "1",
    unit_number: "S0",
    unit_type: "studio",
    bedrooms: "0",
    bathrooms: "1.5",
    rent_amount: "12000",
  };
  assert.deepEqual(validateUnitForm(validUnit, { requireDetails: true }), {});
  assert.equal(
    validateUnitForm(
      { ...validUnit, rent_amount: "12000.123" },
      { requireDetails: true, currency: "USD" }
    ).rent_amount,
    "Monthly rent may have at most 2 decimal places for USD."
  );
  assert.deepEqual(
    validateUnitForm(
      { ...validUnit, rent_amount: "12000.123" },
      { requireDetails: true, currency: "KWD" }
    ),
    {}
  );
  assert.equal(
    validateUnitForm({ ...validUnit, rent_amount: "0" }, { requireDetails: true }).rent_amount,
    "Monthly rent must be greater than zero."
  );
  assert.equal(
    validateUnitForm({ ...validUnit, bathrooms: "1.25" }, { requireDetails: true }).bathrooms,
    "Bathrooms may have at most one decimal place."
  );
  assert.equal(formatUnitType(null, 0), "Studio / bedsitter");
});
