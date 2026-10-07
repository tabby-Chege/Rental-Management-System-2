const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";
// Tabby's login flow should store the JWT under this key.
export const TOKEN_KEY = "access_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const token = getToken();
  if (!token) throw new Error("Please log in to continue.");

  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...options.headers,
      },
    });
  } catch {
    throw new Error("Could not reach the server. Please check your connection.");
  }

  let data = {};
  try {
    data = await res.json();
  } catch {
    // Some error responses have no JSON body.
  }

  if (!res.ok) {
    if (res.status === 401 || res.status === 422) {
      throw new Error("Your session has expired. Please log in again.");
    }
    throw new Error(data.error || `Request failed (${res.status}).`);
  }
  return data;
}

export const getCurrentUser = () => request("/api/auth/me").then((d) => d.user);
export const listTenants = () => request("/api/tenants").then((d) => d.tenants);
export const getMyTenant = () => request("/api/tenants/me").then((d) => d.tenant);

export const createTenant = (body) =>
  request("/api/tenants", { method: "POST", body: JSON.stringify(body) }).then((d) => d.tenant);

export const updateTenant = (id, body) =>
  request(`/api/tenants/${id}`, { method: "PUT", body: JSON.stringify(body) }).then((d) => d.tenant);

export const deleteTenant = (id) => request(`/api/tenants/${id}`, { method: "DELETE" });
