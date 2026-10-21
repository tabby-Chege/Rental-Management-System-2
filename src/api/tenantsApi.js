import { authenticatedFetch } from "./authAPI.js";

async function request(path, options = {}) {
  const response = await authenticatedFetch(`/api/tenants${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  let body = null;
  try {
    body = await response.json();
  } catch {
    // Some successful responses may not include JSON.
  }

  if (!response.ok) {
    const error = new Error(
      body?.error || body?.msg || `Request failed (${response.status})`
    );
    error.status = response.status;
    throw error;
  }

  return body;
}

export async function listTenants(page = 1, perPage = 10) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  return request(`?${params.toString()}`);
}

export async function getMyTenant() {
  return request("/me");
}

export async function updateMyTenant(values) {
  return request("/me", { method: "PUT", body: JSON.stringify(values) });
}

export async function updateTenant(id, values) {
  return request(`/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(values),
  });
}

export async function deleteTenant(id) {
  return request(`/${encodeURIComponent(id)}`, { method: "DELETE" });
}
