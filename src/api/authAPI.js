const TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const API_URL = "/api/auth";
let refreshPromise = null;

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function saveToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function saveTokens(accessToken, refreshToken) {
  saveToken(accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function refreshSession() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const response = await fetch(`${API_URL}/refresh`, {
        method: "POST",
        headers: { Authorization: `Bearer ${refreshToken}` },
      });
      if (!response.ok) {
        clearToken();
        return null;
      }
      const data = await response.json();
      if (!data.access_token || !data.refresh_token) {
        clearToken();
        return null;
      }
      saveTokens(data.access_token, data.refresh_token);
      return data.access_token;
    })();
  }
  const currentRefresh = refreshPromise;
  try {
    return await currentRefresh;
  } finally {
    if (refreshPromise === currentRefresh) refreshPromise = null;
  }
}

export async function authenticatedFetch(url, options = {}) {
  const send = (token) => {
    const headers = { ...options.headers };
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(url, { ...options, headers });
  };

  const response = await send(getToken());
  if (response.status !== 401) return response;

  const accessToken = await refreshSession();
  return accessToken ? send(accessToken) : response;
}

async function authRequest(
  endpoint,
  values = {},
  requiresToken = false,
) {
  let response;
  try {
    const options = {
      method: endpoint === "/me" ? "GET" : "POST",
      headers: { "Content-Type": "application/json" },
      ...(endpoint === "/me" ? {} : { body: JSON.stringify(values) }),
    };
    response = requiresToken
      ? await authenticatedFetch(`${API_URL}${endpoint}`, options)
      : await fetch(`${API_URL}${endpoint}`, options);
  } catch {
    throw new Error("Could not reach the API server. Please try again.");
  }

  let data = {};

  try {
    data = await response.json();
  } catch {
    // Keep an empty response if the server does not return JSON.
  }

  if (!response.ok) {
    throw new Error(data.error || data.msg || "Authentication request failed.");
  }

  return data;
}

export async function registerUser(values) {
  const data = await authRequest("/register", values);

  if (!data.user) {
    throw new Error("Registration response did not include the created user.");
  }
  return data;
}

export async function loginUser(values) {
  const data = await authRequest("/login", values);

  if (!data.access_token || !data.refresh_token) {
    throw new Error("Login response did not include authentication tokens.");
  }

  saveTokens(data.access_token, data.refresh_token);
  return data;
}

export async function getCurrentUser() {
  return authRequest("/me", {}, true);
}

export async function logoutUser() {
  const refreshToken = getRefreshToken();
  clearToken();
  if (!refreshToken) return;

  let response;
  try {
    response = await fetch(`${API_URL}/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${refreshToken}` },
    });
  } catch {
    throw new Error("Could not reach the API to revoke the refresh token.");
  }

  if (!response.ok) {
    throw new Error("The API could not revoke the refresh token.");
  }
}
