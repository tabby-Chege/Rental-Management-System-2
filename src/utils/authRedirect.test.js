import assert from "node:assert/strict";
import test from "node:test";

import { safeReturnTo } from "./authRedirect.js";

test("safeReturnTo preserves an internal path, query, and fragment", () => {
  assert.equal(
    safeReturnTo("/properties/12?intent=apply&unit_id=4#unit-4"),
    "/properties/12?intent=apply&unit_id=4#unit-4",
  );
});

test("safeReturnTo rejects external and protocol-relative destinations", () => {
  assert.equal(safeReturnTo("https://example.com/"), null);
  assert.equal(safeReturnTo("//example.com/"), null);
  assert.equal(safeReturnTo("/\\\\example.com/"), null);
});
