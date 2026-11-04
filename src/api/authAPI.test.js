import assert from "node:assert/strict";
import test from "node:test";

import {
  beginTwoFactorSetup,
  beginGitHubLogin,
  completeTwoFactor,
  getGitHubOAuthConfig,
  getFactorMethods,
  getCurrentUser,
  getRefreshToken,
  getToken,
  loginUser,
  loginWithGitHub,
  loginWithGoogle,
  registerUser,
  sendLoginFactorCode,
  verifyLoginFactorCode,
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

test("password login sends credentials and stores no tokens before verification", async () => {
  const storage = mockBrowser();
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return mockResponse({
      mfa_required: true,
      factor_step: "email_otp",
      challenge_token: "email-challenge",
    });
  };

  const response = await loginUser({
    email: "tenant@example.com",
    password: "ExamplePassword!1",
  });

  assert.equal(response.factor_step, "email_otp");
  assert.equal(response.challenge_token, "email-challenge");
  assert.deepEqual(calls, [
    {
      url: "/api/auth/login",
      body: { email: "tenant@example.com", password: "ExamplePassword!1" },
    },
  ]);
  assert.equal(storage.get("access_token"), undefined);
  assert.equal(storage.get("refresh_token"), undefined);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("registration starts email verification without storing session tokens", async () => {
  const storage = mockBrowser();
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/auth/register");
    assert.equal(options.method, "POST");
    return mockResponse({
      message: "Account created",
      user: { id: 8, role: "tenant" },
      mfa_required: true,
      factor_step: "email_otp",
      flow: "registration",
      challenge_token: "registration-challenge",
    }, 201);
  };

  const response = await registerUser({
    name: "Tenant",
    email: "tenant@example.com",
    password: "ExamplePassword!1",
    role: "tenant",
  });

  assert.equal(response.flow, "registration");
  assert.equal(response.factor_step, "email_otp");
  assert.equal(storage.get("access_token"), undefined);
  assert.equal(storage.get("refresh_token"), undefined);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("password login preserves backend authentication errors", async () => {
  mockBrowser();
  globalThis.fetch = async () =>
    mockResponse({ error: "Invalid email or password" }, 401);

  await assert.rejects(
    loginUser({ email: "tenant@example.com", password: "ExamplePassword!1" }),
    { message: "Invalid email or password" },
  );
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

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

test("login requires TOTP completion before saving session tokens", async () => {
  const storage = mockBrowser();
  const replies = [
    {
      mfa_required: true,
      factor_step: "email_otp",
      challenge_token: "email-challenge",
    },
    {
      mfa_setup_required: true,
      factor_step: "authenticator_enrollment",
      challenge_token: "setup-challenge",
    },
    { secret: "TOTP-SECRET", provisioning_uri: "otpauth://totp/example" },
    {
      user: { id: 8, role: "landlord" },
      access_token: "access",
      refresh_token: "refresh",
    },
  ];
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: options.body ? JSON.parse(options.body) : null });
    return mockResponse(replies.shift());
  };

  const login = await loginUser({ email: "landlord@example.com", password: "Password!123" });
  assert.equal(login.factor_step, "email_otp");
  assert.equal(getToken(), null);
  const emailVerified = await verifyLoginFactorCode(
    "email-challenge",
    "email",
    "123456",
  );
  assert.equal(emailVerified.factor_step, "authenticator_enrollment");
  assert.equal(getToken(), null);
  assert.deepEqual(await beginTwoFactorSetup("setup-challenge"), {
    secret: "TOTP-SECRET",
    provisioning_uri: "otpauth://totp/example",
  });
  const completed = await completeTwoFactor("setup-challenge", "123456", true);

  assert.equal(completed.user.role, "landlord");
  assert.equal(getToken(), "access");
  assert.equal(getRefreshToken(), "refresh");
  assert.deepEqual(calls.map(({ url }) => url), [
    "/api/auth/login",
    "/api/auth/two-factor/code/verify",
    "/api/auth/two-factor/setup",
    "/api/auth/two-factor/confirm",
  ]);
  assert.deepEqual(calls[3].body, {
    challenge_token: "setup-challenge",
    code: "123456",
  });
  assert.equal(storage.get("access_token"), "access");
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("Google login sends role only when selected for a new account", async () => {
  mockBrowser();
  const calls = [];
  const replies = [
    { role_required: true },
    {
      mfa_required: true,
      factor_step: "email_otp",
      challenge_token: "google-mfa",
    },
  ];
  globalThis.fetch = async (url, options) => {
    calls.push(JSON.parse(options.body));
    return mockResponse(replies.shift());
  };

  assert.deepEqual(await loginWithGoogle("google-id-token"), { role_required: true });
  assert.deepEqual(await loginWithGoogle("google-id-token", "tenant"), {
    mfa_required: true,
    factor_step: "email_otp",
    challenge_token: "google-mfa",
  });
  assert.deepEqual(calls, [
    { credential: "google-id-token" },
    { credential: "google-id-token", role: "tenant" },
  ]);
  assert.equal(getToken(), null);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("GitHub OAuth does not save a session before the MFA challenge is completed", async () => {
  mockBrowser();
  const calls = [];
  const replies = [
    { configured: true },
    { authorization_url: "https://github.com/login/oauth/authorize?state=oauth-state" },
    {
      mfa_required: true,
      factor_step: "email_otp",
      challenge_token: "github-mfa",
    },
  ];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, method: options.method, body: options.body });
    return mockResponse(replies.shift());
  };

  assert.deepEqual(await getGitHubOAuthConfig(), { configured: true });
  assert.equal(
    (await beginGitHubLogin()).authorization_url,
    "https://github.com/login/oauth/authorize?state=oauth-state",
  );
  assert.deepEqual(await loginWithGitHub("oauth-code", "oauth-state", "tenant"), {
    mfa_required: true,
    factor_step: "email_otp",
    challenge_token: "github-mfa",
  });
  assert.equal(getToken(), null);
  assert.deepEqual(
    calls.map(({ url, method, body }) => ({
      url,
      method,
      body: body ? JSON.parse(body) : null,
    })),
    [
      { url: "/api/auth/github-login/config", method: "GET", body: null },
      { url: "/api/auth/github-login/start", method: "POST", body: {} },
      {
        url: "/api/auth/github-login",
        method: "POST",
        body: { code: "oauth-code", state: "oauth-state", role: "tenant" },
      },
    ],
  );
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("email factor verification advances to TOTP without storing session tokens", async () => {
  const storage = mockBrowser();
  const calls = [];
  const replies = [
    { message: "A verification code was queued for delivery by email." },
    {
      mfa_required: true,
      factor_step: "authenticator_totp",
      challenge_token: "totp-challenge",
    },
  ];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return mockResponse(replies.shift());
  };

  await sendLoginFactorCode("login-challenge", "email");
  const verified = await verifyLoginFactorCode(
    "login-challenge",
    "email",
    "123456",
  );

  assert.equal(verified.factor_step, "authenticator_totp");
  assert.equal(verified.challenge_token, "totp-challenge");
  assert.equal(storage.get("access_token"), undefined);
  assert.equal(storage.get("refresh_token"), undefined);
  assert.deepEqual(calls, [
    {
      url: "/api/auth/two-factor/code/send",
      body: { challenge_token: "login-challenge", method: "email" },
    },
    {
      url: "/api/auth/two-factor/code/verify",
      body: {
        challenge_token: "login-challenge",
        method: "email",
        code: "123456",
      },
    },
  ]);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("factor settings are fetched with an authenticated GET request", async () => {
  mockBrowser({ access_token: "mfa-access" });
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return mockResponse({ methods: [{ id: "totp", label: "Authenticator app" }] });
  };

  assert.deepEqual(await getFactorMethods(), {
    methods: [{ id: "totp", label: "Authenticator app" }],
  });
  assert.equal(request.url, "/api/auth/two-factor/methods");
  assert.equal(request.options.method, "GET");
  assert.equal(request.options.headers.Authorization, `Bearer ${getToken()}`);
  delete globalThis.localStorage;
  delete globalThis.fetch;
});
