import { authenticatedFetch } from "./authAPI.js";

async function request(path, options = {}, baseUrl = "/api/properties") {
  const response = await authenticatedFetch(`${baseUrl}${path}`, {
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
  scope = "",
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (scope) params.set("scope", scope);
  if (q.trim()) params.set("q", q.trim());
  if (city.trim()) params.set("city", city.trim());

  return request(`?${params.toString()}`);
}

export function getPropertiesSummary() {
  return request("/summary");
}

export function listPublicProperties({
  page = 1,
  perPage = 10,
  q = "",
  city = "",
  minRent = "",
  maxRent = "",
  bedrooms = "",
  available = "",
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (q.trim()) params.set("q", q.trim());
  if (city.trim()) params.set("city", city.trim());
  if (String(minRent).trim()) params.set("min_rent", String(minRent).trim());
  if (String(maxRent).trim()) params.set("max_rent", String(maxRent).trim());
  if (String(bedrooms).trim()) params.set("bedrooms", String(bedrooms).trim());
  if (available) params.set("available", String(available));

  return request(`?${params.toString()}`, {}, "/api/properties/public");
}

export function listPublicUnits({
  page = 1,
  perPage = 10,
  q = "",
  location = "",
  bedrooms = "",
  bathrooms = "",
  minRent = "",
  maxRent = "",
  unitType = "",
  availability = "vacant",
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
    availability,
  });
  if (q.trim()) params.set("q", q.trim());
  if (location.trim()) params.set("location", location.trim());
  if (String(bedrooms).trim()) params.set("bedrooms", String(bedrooms).trim());
  if (String(bathrooms).trim()) params.set("bathrooms", String(bathrooms).trim());
  if (String(minRent).trim()) params.set("min_rent", String(minRent).trim());
  if (String(maxRent).trim()) params.set("max_rent", String(maxRent).trim());
  if (unitType) params.set("unit_type", unitType);
  return request(`?${params.toString()}`, {}, "/api/units/public");
}

export async function getProperty(id) {
  const data = await request(`/${encodeURIComponent(id)}`);
  return data.property;
}

export async function getPublicProperty(id) {
  const data = await request(
    `/${encodeURIComponent(id)}`,
    {},
    "/api/properties/public"
  );
  return data.property;
}

export async function listPublicPropertyUnits(propertyId, { unitId } = {}) {
  const params = unitId
    ? new URLSearchParams({ unit_id: String(unitId) })
    : new URLSearchParams({ page: "1", per_page: "100" });
  const path = `/${encodeURIComponent(propertyId)}/units`;
  const firstPage = await request(
    `${path}?${params.toString()}`,
    {},
    "/api/properties/public"
  );
  if (unitId || !firstPage.pagination) return firstPage;

  const units = [...firstPage.units];
  for (let page = 2; page <= firstPage.pagination.pages; page += 1) {
    params.set("page", String(page));
    const result = await request(
      `${path}?${params.toString()}`,
      {},
      "/api/properties/public"
    );
    units.push(...result.units);
  }
  return { ...firstPage, units };
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
