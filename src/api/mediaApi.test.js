import assert from "node:assert/strict";
import test from "node:test";

import {
  photoUrl,
  reportListing,
  uploadPropertyPhoto,
  uploadUnitPhoto,
} from "./mediaApi.js";

function mockBrowser() {
  globalThis.localStorage = {
    getItem: (key) => (key === "access_token" ? "media-test-token" : null),
    setItem: () => {},
    removeItem: () => {},
  };
}

function mockResponse(body) {
  return new Response(JSON.stringify(body), {
    status: 201,
    headers: { "Content-Type": "application/json" },
  });
}

test("property and unit photo uploads send multipart data with authentication", async () => {
  mockBrowser();
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return mockResponse({ photo: { id: calls.length } });
  };
  const file = new Blob(["image bytes"], { type: "image/png" });

  await uploadPropertyPhoto(12, file);
  await uploadUnitPhoto(34, file, { roomId: 5 });

  assert.deepEqual(
    calls.map(({ url }) => url),
    ["/api/properties/12/photos", "/api/units/34/photos"],
  );
  assert.equal(calls[0].options.headers.Authorization, "Bearer media-test-token");
  assert.equal(calls[0].options.headers["Content-Type"], undefined);
  const uploadedFile = calls[0].options.body.get("file");
  assert.equal(uploadedFile.type, "image/png");
  assert.equal(await uploadedFile.text(), "image bytes");
  assert.equal(calls[1].options.body.get("room_id"), "5");
  assert.equal(calls[1].options.body.get("is_cover"), null);

  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("listing reports send a JSON body and photo URLs are preserved", async () => {
  mockBrowser();
  let requestOptions;
  globalThis.fetch = async (_url, options) => {
    requestOptions = options;
    return mockResponse({ report: { id: 1 } });
  };

  const report = { property_id: 12, reason: "inaccurate", details: "Wrong rent" };
  assert.deepEqual(await reportListing(report), { report: { id: 1 } });
  assert.equal(requestOptions.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(requestOptions.body), report);
  assert.equal(photoUrl({ url: "/api/public/photos/8" }), "/api/public/photos/8");

  delete globalThis.localStorage;
  delete globalThis.fetch;
});
