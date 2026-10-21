import assert from "node:assert/strict";
import test from "node:test";

import {
  currencyPrecision,
  formatMoney,
  makeInternationalPhone,
  phoneParts,
} from "./money.js";

test("money formatting follows currency-specific digits and symbols", () => {
  assert.equal(currencyPrecision("USD"), 2);
  assert.equal(currencyPrecision("JPY"), 0);
  assert.equal(currencyPrecision("KWD"), 3);
  assert.equal(
    formatMoney(1234.5, "USD"),
    new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(1234.5)
  );
  assert.equal(
    formatMoney(1234, "JPY"),
    new Intl.NumberFormat(undefined, { style: "currency", currency: "JPY" }).format(1234)
  );
});

test("phone code picker values create E.164 numbers and split saved numbers", () => {
  assert.equal(makeInternationalPhone("+254", "0712 345 678"), "+254712345678");
  assert.deepEqual(phoneParts("+447123456789"), {
    dialCode: "+44",
    number: "7123456789",
  });
  assert.deepEqual(phoneParts("+358401234567"), {
    dialCode: "custom",
    number: "+358401234567",
  });
  assert.equal(makeInternationalPhone("custom", "+358401234567"), "+358401234567");
});
