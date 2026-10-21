import assert from "node:assert/strict";
import test from "node:test";

import {
  getMyTenantProfile,
  updateMyTenantProfile,
  uploadTenantDocument,
} from "./tenantProfilesApi.js";

function mockResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("tenant profile API includes auth and serializes profile changes", async () => {
  globalThis.localStorage = {
    getItem: (key) => (key === "access_token" ? "profile-token" : null),
    setItem: () => {},
    removeItem: () => {},
  };
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return mockResponse({ profile: { full_name: "Tenant" }, documents: [] });
  };

  assert.deepEqual(await getMyTenantProfile(), {
    profile: { full_name: "Tenant" },
    documents: [],
  });
  await uploadTenantDocument(new Blob(["document"]), "identity");

  assert.equal(calls[0].url, "/api/tenant-profile/me");
  assert.equal(calls[0].options.headers.Authorization, "Bearer profile-token");
  assert.equal(calls[1].url, "/api/tenant-profile/me/documents");
  assert.equal(calls[1].options.headers.Authorization, "Bearer profile-token");
  assert.equal(calls[1].options.headers["Content-Type"], undefined);
  assert.ok(calls[1].options.body instanceof FormData);

  await updateMyTenantProfile({
    full_name: "Tenant",
    id_type: "passport",
    has_id_number: true,
    updated_at: "2026-10-21T00:00:00Z",
    user_id: 17,
  });
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    full_name: "Tenant",
    id_type: "passport",
  });
  delete globalThis.localStorage;
  delete globalThis.fetch;
});
