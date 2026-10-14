const TOKEN_KEY = "access_token";
const API_URL = "/api/auth";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function saveToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function authRequest(endpoint, values = {}, requiresToken = false) {
  const token = getToken();

  const headers = {
    "Content-Type": "application/json",
  };

  if (requiresToken && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    method: endpoint === "/me" ? "GET" : "POST",
    headers,
    ...(endpoint === "/me" ? {} : { body: JSON.stringify(values) }),
  });

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

  if (!data.access_token) {
    throw new Error("Registration response did not include an access token.");
  }

  saveToken(data.access_token);
  return data;
}

export async function loginUser(values) {
  const data = await authRequest("/login", values);

  if (!data.access_token) {
    throw new Error("Login response did not include an access token.");
  }

  saveToken(data.access_token);
  return data;
}

export async function getCurrentUser() {
  return authRequest("/me", {}, true);
}

export function logoutUser() {
  clearToken();
}
