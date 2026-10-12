import sampleProperties from "../data/sampleProperties.json";
import { filterByLocation } from "../utils/propertySearch";

const BASE_URL = "https://api.rentcast.io/v1";
const API_KEY = import.meta.env.VITE_RENTCAST_API_KEY;
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

// Remembers results so the same search doesn't use another request
const cache = new Map();

async function request(path, params = {}) {
  const query = new URLSearchParams(params).toString();
  const url = `${BASE_URL}${path}${query ? `?${query}` : ""}`;

  if (cache.has(url)) return cache.get(url);
  if (!API_KEY) {
    throw new Error("RentCast API key is missing. Set VITE_RENTCAST_API_KEY and reload.");
  }

  let res;
  try {
    res = await fetch(url, {
      headers: { "X-Api-Key": API_KEY, Accept: "application/json" },
    });
  } catch {
    throw new Error("Network error. Please check your connection.");
  }

  if (res.status === 401) throw new Error("Missing or invalid API key.");
  if (res.status === 429) throw new Error("Too many requests. Try again later.");
  if (!res.ok) throw new Error(`Request failed (${res.status})`);

  const data = await res.json();
  cache.set(url, data);
  return data;
}

// Returns an array of properties for a US city, e.g. searchProperties("Austin", "TX")
export async function searchProperties(city, state, limit = 20) {
  if (USE_MOCK) return filterByLocation(sampleProperties, city, state, limit);
  return request("/properties", { city, state, limit });
}

// Returns one property by id, or null in mock mode if not found
export async function getPropertyById(id) {
  if (USE_MOCK) return sampleProperties.find((p) => p.id === id) ?? null;
  return request(`/properties/${encodeURIComponent(id)}`);
}