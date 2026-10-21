import { request } from "./client.js";

export async function listUnits(propertyId) {
  const params = new URLSearchParams({ page: "1", per_page: "100" });
  if (propertyId) params.set("property_id", String(propertyId));
  const firstPage = await request(`/api/units?${params.toString()}`);
  const units = [...firstPage.units];
  for (let page = 2; page <= firstPage.pagination.pages; page += 1) {
    params.set("page", String(page));
    const result = await request(`/api/units?${params.toString()}`);
    units.push(...result.units);
  }
  return units;
}

export const getUnit = (id) => request(`/api/units/${id}`).then((d) => d.unit ?? d);

export const createUnit = (body) =>
  request("/api/units", { method: "POST", body: JSON.stringify(body) }).then((d) => d.unit ?? d);

export const bulkCreateUnits = (propertyId, body) =>
  request(`/api/properties/${propertyId}/units/bulk`, {
    method: "POST",
    body: JSON.stringify(body),
  }).then((data) => data.units);

export const updateUnit = (id, body) =>
  request(`/api/units/${id}`, { method: "PUT", body: JSON.stringify(body) }).then((d) => d.unit ?? d);

export const deleteUnit = (id) => request(`/api/units/${id}`, { method: "DELETE" });

export const createRoom = (unitId, body) =>
  request(`/api/units/${unitId}/rooms`, {
    method: "POST",
    body: JSON.stringify(body),
  }).then((data) => data.room);

export const updateRoom = (id, body) =>
  request(`/api/rooms/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  }).then((data) => data.room);

export const deleteRoom = (id) =>
  request(`/api/rooms/${id}`, { method: "DELETE" });

// Sonia's endpoint: GET /api/properties -> { properties: [...] } (landlords see their own, admins all).
export async function listProperties() {
  const params = new URLSearchParams({ page: "1", per_page: "100" });
  const firstPage = await request(`/api/properties?${params.toString()}`);
  const properties = [...firstPage.properties];
  for (let page = 2; page <= firstPage.pagination.pages; page += 1) {
    params.set("page", String(page));
    const result = await request(`/api/properties?${params.toString()}`);
    properties.push(...result.properties);
  }
  return properties;
}
