import test from "node:test";
import assert from "node:assert/strict";
import { validateTenantForm } from "./tenantForm.js";

const ok = { name: "Tess", email: "tess@x.com", phone: "0712 345 678" };

test("accepts a valid form", () => {
  assert.deepEqual(validateTenantForm(ok), {});
});

test("requires a name unless told otherwise", () => {
  assert.ok(validateTenantForm({ ...ok, name: " " }).name);
  assert.deepEqual(validateTenantForm({ ...ok, name: "" }, { requireName: false }), {});
});

test("rejects bad emails", () => {
  assert.ok(validateTenantForm({ ...ok, email: "nope" }).email);
  assert.ok(validateTenantForm({ ...ok, email: "a@b" }).email);
});

test("phone is optional but must look like a phone number", () => {
  assert.deepEqual(validateTenantForm({ ...ok, phone: "" }), {});
  assert.ok(validateTenantForm({ ...ok, phone: "abc" }).phone);
});
