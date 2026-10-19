import assert from "node:assert/strict";
import test from "node:test";

import { listPayments } from "./paymentsAPI.js";

test("payment history request sends pagination and bearer authorization", async () => {
  globalThis.localStorage = { getItem: () => "test-token" };
  let requestedUrl;
  let requestedOptions;
  globalThis.fetch = async (url, options) => {
    requestedUrl = url;
    requestedOptions = options;
    return new Response(JSON.stringify({ payments: [], pagination: { total: 0 } }), {
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await listPayments({ page: 2, perPage: 5 });
  assert.equal(requestedUrl, "/api/payments?page=2&per_page=5");
  assert.equal(requestedOptions.headers.Authorization, "Bearer test-token");
  assert.deepEqual(result.payments, []);
  assert.equal(result.pagination.total, 0);

  delete globalThis.localStorage;
  delete globalThis.fetch;
});
