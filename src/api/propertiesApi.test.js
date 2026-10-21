import assert from "node:assert/strict";
import test from "node:test";

import {
  createProperty,
  deleteProperty,
  getProperty,
  getPublicProperty,
  getPropertiesSummary,
  listPublicUnits,
  listProperties,
  listPublicProperties,
  listPublicPropertyUnits,
  updateProperty,
} from "./propertiesApi.js";

function mockBrowser(token = "test-token") {
  const storage = new Map([["access_token", token]]);
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
}

function mockResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("property list sends pagination, search, and authorization", async () => {
  mockBrowser();
  let requestedUrl;
  let requestedHeaders;
  globalThis.fetch = async (url, options) => {
    requestedUrl = url;
    requestedHeaders = options.headers;
    return mockResponse({ properties: [], pagination: { page: 2 } });
  };

  const result = await listProperties({
    page: 2,
    perPage: 5,
    q: "Oak Lane",
    city: "Nairobi",
  });

  assert.equal(
    requestedUrl,
    "/api/properties?page=2&per_page=5&q=Oak+Lane&city=Nairobi"
  );
  assert.equal(requestedHeaders.Authorization, "Bearer test-token");
  assert.deepEqual(result.pagination, { page: 2 });
});

test("public search and property detail use the public listing endpoints", async () => {
  mockBrowser();
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (url.includes("/units")) {
      return mockResponse({ units: [{ id: 11 }] });
    }
    if (url.includes("?")) {
      return mockResponse({ properties: [], pagination: { total: 0 } });
    }
    return mockResponse({ property: { id: 7 } });
  };

  await listPublicProperties({
    city: "Nairobi",
    minRent: "500",
    bedrooms: "2",
    available: "true",
  });

  assert.deepEqual(await getPublicProperty(7), { id: 7 });
  assert.deepEqual(await listPublicPropertyUnits(7, { unitId: 11 }), { units: [{ id: 11 }] });
  assert.equal(
    calls[0],
    "/api/properties/public?page=1&per_page=10&city=Nairobi&min_rent=500&bedrooms=2&available=true"
  );
  assert.deepEqual(calls.slice(1), [
    "/api/properties/public/7",
    "/api/properties/public/7/units?unit_id=11",
  ]);

  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("public property detail loads units across every result page", async () => {
  mockBrowser();
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    const page = new URL(url, "http://localhost").searchParams.get("page");
    return mockResponse({
      units: [{ id: Number(page) }],
      pagination: { pages: 2 },
    });
  };

  const result = await listPublicPropertyUnits(7);
  assert.deepEqual(result.units, [{ id: 1 }, { id: 2 }]);
  assert.deepEqual(calls, [
    "/api/properties/public/7/units?page=1&per_page=100",
    "/api/properties/public/7/units?page=2&per_page=100",
  ]);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("public unit search sends unit-level filters and defaults to vacant inventory", async () => {
  mockBrowser();
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return mockResponse({ units: [], pagination: { total: 0 } });
  };

  const result = await listPublicUnits({
    q: "riverside",
    location: "Nairobi",
    bedrooms: 2,
    bathrooms: 1.5,
    minRent: 10000,
    maxRent: 20000,
    unitType: "two-bedroom",
  });

  const params = new URL(requestedUrl, "http://localhost").searchParams;
  assert.equal(new URL(requestedUrl, "http://localhost").pathname, "/api/units/public");
  assert.equal(params.get("availability"), "vacant");
  assert.equal(params.get("q"), "riverside");
  assert.equal(params.get("location"), "Nairobi");
  assert.equal(params.get("bedrooms"), "2");
  assert.equal(params.get("bathrooms"), "1.5");
  assert.equal(params.get("min_rent"), "10000");
  assert.equal(params.get("max_rent"), "20000");
  assert.equal(params.get("unit_type"), "two-bedroom");
  assert.deepEqual(result.units, []);

  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("property API exposes CRUD operations and surfaces API errors", async () => {
  mockBrowser();
  const calls = [];
  const replies = [
    { property: { id: 7 } },
    { property: { id: 8 } },
    { property: { id: 8 } },
    { message: "Property deleted" },
  ];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, method: options.method || "GET" });
    return mockResponse(replies.shift());
  };

  assert.deepEqual(await getProperty(7), { id: 7 });
  assert.deepEqual(await createProperty({ name: "Home" }), { id: 8 });
  assert.deepEqual(await updateProperty(8, { name: "Updated" }), { id: 8 });
  await deleteProperty(8);
  assert.deepEqual(calls, [
    { url: "/api/properties/7", method: "GET" },
    { url: "/api/properties", method: "POST" },
    { url: "/api/properties/8", method: "PUT" },
    { url: "/api/properties/8", method: "DELETE" },
  ]);

  globalThis.fetch = async () => mockResponse({ error: "Not allowed" }, 403);
  await assert.rejects(listProperties(), {
    message: "Not allowed",
    status: 403,
  });

  test("portfolio summary uses the authenticated property summary endpoint", async () => {
    mockBrowser();
    let requestedUrl;
    globalThis.fetch = async (url) => {
      requestedUrl = url;
      return mockResponse({ occupancy_summary: { total_units: 20 } });
    };

    assert.deepEqual(await getPropertiesSummary(), {
      occupancy_summary: { total_units: 20 },
    });
    assert.equal(requestedUrl, "/api/properties/summary");
    delete globalThis.localStorage;
    delete globalThis.fetch;
  });

  globalThis.fetch = async () => mockResponse({
    error: "Your session has ended. Please sign in again to continue.",
  }, 401);
  await assert.rejects(createProperty({ name: "Home" }), {
    message: "Your session has ended. Please sign in again to continue.",
    status: 401,
  });

  delete globalThis.localStorage;
  delete globalThis.fetch;
});
