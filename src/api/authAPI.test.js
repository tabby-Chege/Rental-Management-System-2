import assert from "node:assert/strict";
import test from "node:test";

import {
  getCurrentUser,
  getRefreshToken,
  getToken,
  logoutUser,
} from "./authAPI.js";

function mockBrowser(initial = {}) {
  const storage = new Map(Object.entries(initial));
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  return storage;
}

function mockResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("protected requests rotate expired access and refresh tokens", async () => {
  const storage = mockBrowser({
    access_token: "expired-access",
    refresh_token: "old-refresh",
  });
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, authorization: options.headers.Authorization });
    if (url === "/api/auth/refresh") {
      return mockResponse({
        access_token: "new-access",
        refresh_token: "new-refresh",
      });
    }
    if (calls.length === 1) return mockResponse({ error: "Expired" }, 401);
    return mockResponse({ user: { id: 1 } });
  };

  assert.deepEqual(await getCurrentUser(), { user: { id: 1 } });
  assert.deepEqual(calls, [
    { url: "/api/auth/me", authorization: "Bearer expired-access" },
    { url: "/api/auth/refresh", authorization: "Bearer old-refresh" },
    { url: "/api/auth/me", authorization: "Bearer new-access" },
  ]);
  assert.equal(storage.get("access_token"), "new-access");
  assert.equal(storage.get("refresh_token"), "new-refresh");
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("logout revokes the refresh token and clears local tokens", async () => {
  const storage = mockBrowser({
    access_token: "access",
    refresh_token: "refresh",
  });
  let authorization;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/auth/logout");
    authorization = options.headers.Authorization;
    return mockResponse({ message: "Signed out successfully" });
  };

  await logoutUser();

  assert.equal(authorization, "Bearer refresh");
  assert.equal(getToken(), null);
  assert.equal(getRefreshToken(), null);
  assert.equal(storage.size, 0);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});
