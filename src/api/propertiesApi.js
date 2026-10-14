import { getToken } from "./authAPI.js";

async function request(path, options = {}) {
  const token = getToken();
  const response = await fetch(`/api/properties${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  let body = null;
  try {
    body = await response.json();
  } catch {
    // Some successful responses, such as DELETE, may not include JSON.
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

export function listProperties({
  page = 1,
  perPage = 10,
  q = "",
  city = "",
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (q.trim()) params.set("q", q.trim());
  if (city.trim()) params.set("city", city.trim());

  return request(`?${params.toString()}`);
}

export async function getProperty(id) {
  const data = await request(`/${encodeURIComponent(id)}`);
  return data.property;
}

export async function createProperty(values) {
  const data = await request("", {
    method: "POST",
    body: JSON.stringify(values),
  });
  return data.property;
}

export async function updateProperty(id, values) {
  const data = await request(`/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(values),
  });
  return data.property;
}

export async function deleteProperty(id) {
  return request(`/${encodeURIComponent(id)}`, { method: "DELETE" });
}
