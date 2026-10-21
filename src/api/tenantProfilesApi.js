import { authenticatedFetch } from "./authAPI.js";

async function parseResponse(response) {
  let data = {};
  try {
    data = await response.json();
  } catch {
    // File downloads are handled separately from JSON responses.
  }
  if (!response.ok) {
    const error = new Error(
      data.error || data.msg || `Request failed (${response.status})`,
    );
    error.status = response.status;
    throw error;
  }
  return data;
}

export async function getMyTenantProfile() {
  const response = await authenticatedFetch("/api/tenant-profile/me");
  return parseResponse(response);
}

export async function updateMyTenantProfile(values) {
  const response = await authenticatedFetch("/api/tenant-profile/me", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  return parseResponse(response);
}

export async function uploadTenantDocument(file, kind = "identity") {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  const response = await authenticatedFetch(
    "/api/tenant-profile/me/documents",
    { method: "POST", body: form },
  );
  return parseResponse(response);
}

export async function deleteTenantDocument(id) {
  const response = await authenticatedFetch(
    `/api/tenant-profile/me/documents/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  return parseResponse(response);
}

export async function downloadTenantDocument(id) {
  const response = await authenticatedFetch(
    `/api/tenant-documents/${encodeURIComponent(id)}`,
  );
  if (!response.ok) return parseResponse(response);
  return response.blob();
}
