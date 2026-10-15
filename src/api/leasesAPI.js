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
  request("/api/leases", { method: "POST", body: JSON.stringify(body) }).then((d) => d.lease ?? d);

export const updateLease = (id, body) =>
  request(`/api/leases/${id}`, { method: "PUT", body: JSON.stringify(body) }).then((d) => d.lease ?? d);

export const deleteLease = (id) => request(`/api/leases/${id}`, { method: "DELETE" });

// Tenant accounts only (role "tenant"): read-only views of their own leases and payments.
export const listMyLeases = () => request("/api/leases/mine").then((d) => d.leases);

// Newest first. Pass a lease id to see the payments for just that lease.
export const listMyPayments = (leaseId) =>
  request(`/api/leases/mine/payments${leaseId ? `?lease_id=${leaseId}` : ""}`).then((d) => d.payments);