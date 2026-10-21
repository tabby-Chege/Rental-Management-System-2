import { authenticatedFetch } from "./authAPI.js";
import { request } from "./client.js";

export function listMaintenanceRequests() {
  return request("/api/maintenance").then((data) => data.requests);
}

export function createMaintenanceRequest(values) {
  return request("/api/maintenance", {
    method: "POST",
    body: JSON.stringify(values),
  }).then((data) => data.request);
}

export function updateMaintenanceStatus(id, status) {
  return request(`/api/maintenance/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  }).then((data) => data.request);
}

export async function uploadMaintenancePhoto(requestId, file) {
  const form = new FormData();
  form.append("file", file);
  const response = await authenticatedFetch(
    `/api/maintenance/${encodeURIComponent(requestId)}/photos`,
    { method: "POST", body: form },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return response.json();
}

export async function downloadPrivateFile(url, filename) {
  const response = await authenticatedFetch(url);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

export async function listLeaseDocuments(leaseId) {
  return request(`/api/leases/${encodeURIComponent(leaseId)}/documents`)
    .then((data) => data.documents);
}

export async function uploadLeaseDocument(leaseId, file) {
  const form = new FormData();
  form.append("file", file);
  const response = await authenticatedFetch(
    `/api/leases/${encodeURIComponent(leaseId)}/documents`,
    { method: "POST", body: form },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return response.json();
}

export function getPortfolioReport() {
  return request("/api/reports/portfolio");
}
