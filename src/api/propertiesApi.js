// Talks to OUR Flask backend (not RentCast). Requests go to /api/..., which the
// Vite dev server proxies to Flask (see vite.config.js).

// Tabby's login page must save the JWT under this exact key after login:
//   localStorage.setItem("access_token", data.access_token)
export const TOKEN_KEY = "access_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

async function request(path, options = {}) {
  const token = getToken();

  const response = await fetch(`/api/properties${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  let body = null;
  try {
    body = await response.json();
  } catch {
    // response had no JSON body
  }

  if (!response.ok) {
    // Our routes send {error}; flask-jwt-extended sends {msg} for token problems.
    const error = new Error(
      body?.error || body?.msg || `Request failed (${response.status})`
    );
    error.status = response.status;
    throw error;
  }

  return body;
}

export async function listProperties() {
  const data = await request("");
  return data.properties;
}

export async function createProperty(values) {
  const data = await request("", {
    method: "POST",
    body: JSON.stringify(values),
  });
  return data.property;
}

export async function updateProperty(id, values) {
  const data = await request(`/${id}`, {
    method: "PUT",
    body: JSON.stringify(values),
  });
  return data.property;
}

export async function deleteProperty(id) {
  await request(`/${id}`, { method: "DELETE" });
}
