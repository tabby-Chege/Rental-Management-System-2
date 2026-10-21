// Shared fetch helper for the units and leases API files.
// Same behaviour as tenantsAPI.js: reads token from localStorage, {"error": "..."} messages.
import { authenticatedFetch, getToken } from "./authAPI.js";

const BASE_URL = import.meta.env?.VITE_API_URL || "";

export async function request(path, options = {}) {
  const token = getToken();
  if (!token) throw new Error("Please log in to continue.");

  let res;
  try {
    res = await authenticatedFetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
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
      throw new Error("Your session has ended. Please sign in again to continue.");
    }
    throw new Error(data.error || `Request failed (${res.status}).`);
  }
  return data;
}
