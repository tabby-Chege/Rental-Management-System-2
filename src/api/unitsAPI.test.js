import assert from "node:assert/strict";
import test from "node:test";

import { bulkCreateUnits, listUnits } from "./unitsAPI.js";

test("unit listing loads all pages for properties with more than 100 units", async () => {
  globalThis.localStorage = {
    getItem: (key) => (key === "access_token" ? "test-token" : null),
    setItem: () => {},
    removeItem: () => {},
  };
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    const page = new URL(url, "http://localhost").searchParams.get("page");
    return new Response(JSON.stringify({
      units: [{ id: Number(page) }],
      pagination: { pages: 2 },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  };

  assert.deepEqual(await listUnits(7), [{ id: 1 }, { id: 2 }]);
  assert.deepEqual(calls, [
    "/api/units?page=1&per_page=100&property_id=7",
    "/api/units?page=2&per_page=100&property_id=7",
  ]);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("bulk unit creation posts the previewed layout and rent", async () => {
  globalThis.localStorage = {
    getItem: (key) => (key === "access_token" ? "test-token" : null),
    setItem: () => {},
    removeItem: () => {},
  };
  let requestedUrl;
  let requestedBody;
  globalThis.fetch = async (url, options) => {
    requestedUrl = url;
    requestedBody = JSON.parse(options.body);
    return new Response(JSON.stringify({ units: [{ id: 1 }] }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  assert.deepEqual(
    await bulkCreateUnits(7, {
      units_per_floor: 5,
      layout: "2+1",
      rent_amount: 18000,
    }),
    [{ id: 1 }]
  );
  assert.equal(requestedUrl, "/api/properties/7/units/bulk");
  assert.deepEqual(requestedBody, {
    units_per_floor: 5,
    layout: "2+1",
    rent_amount: 18000,
  });
  delete globalThis.localStorage;
  delete globalThis.fetch;
});
