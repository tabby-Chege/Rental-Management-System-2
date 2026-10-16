import assert from "node:assert/strict";
import test from "node:test";

import {
  createProperty,
  deleteProperty,
  getProperty,
  getPublicProperty,
  listProperties,
  listPublicProperties,
  listPublicPropertyUnits,
  updateProperty,
} from "./propertiesApi.js";

function mockBrowser(token = "test-token") {
  globalThis.localStorage = {
    getItem: () => token,
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
  assert.deepEqual(await listPublicPropertyUnits(7), { units: [{ id: 11 }] });
  assert.equal(
    calls[0],
    "/api/properties/public?page=1&per_page=10&city=Nairobi&min_rent=500&bedrooms=2&available=true"
  );
  assert.deepEqual(calls.slice(1), [
    "/api/properties/public/7",
    "/api/properties/public/7/units",
  ]);

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

  delete globalThis.localStorage;
  delete globalThis.fetch;
});
