import assert from "node:assert/strict";
import test from "node:test";

import {
  createProperty,
  deleteProperty,
  getProperty,
  listProperties,
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
