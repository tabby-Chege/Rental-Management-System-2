import { request } from "./client";

// Filters are all optional: { tenantId, unitId, status }
export function listLeases({ tenantId, unitId, status } = {}) {
  const params = new URLSearchParams();
  if (tenantId) params.set("tenant_id", tenantId);
  if (unitId) params.set("unit_id", unitId);
  if (status) params.set("status", status);
  const query = params.toString();
  return request(`/api/leases${query ? `?${query}` : ""}`).then((d) => d.leases);
}

export const getLease = (id) => request(`/api/leases/${id}`).then((d) => d.lease);

export const createLease = (body) =>
  request("/api/leases", { method: "POST", body: JSON.stringify(body) }).then((d) => d.lease);

export const updateLease = (id, body) =>
  request(`/api/leases/${id}`, { method: "PUT", body: JSON.stringify(body) }).then((d) => d.lease);

export const deleteLease = (id) => request(`/api/leases/${id}`, { method: "DELETE" });
