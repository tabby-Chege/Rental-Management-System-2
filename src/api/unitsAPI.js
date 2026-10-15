import { request } from "./client";

export const listUnits = (propertyId) =>
  request(`/api/units${propertyId ? `?property_id=${propertyId}` : ""}`).then((d) => d.units);

export const getUnit = (id) => request(`/api/units/${id}`).then((d) => d.unit ?? d);

export const createUnit = (body) =>
  request("/api/units", { method: "POST", body: JSON.stringify(body) }).then((d) => d.unit ?? d);

export const updateUnit = (id, body) =>
  request(`/api/units/${id}`, { method: "PUT", body: JSON.stringify(body) }).then((d) => d.unit ?? d);

export const deleteUnit = (id) => request(`/api/units/${id}`, { method: "DELETE" });

// Sonia's endpoint: GET /api/properties -> { properties: [...] } (landlords see their own, admins all).
export const listProperties = () => request("/api/properties").then((d) => d.properties);
