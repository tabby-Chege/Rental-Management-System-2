import { authenticatedFetch } from "./authAPI.js";

async function mediaRequest(path, options = {}) {
  const response = await authenticatedFetch(path, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    // Successful file responses do not contain JSON.
  }
  if (!response.ok) {
    throw new Error(
      body?.error || body?.msg || `Request failed (${response.status})`,
    );
  }
  return body;
}

export function photoUrl(photo) {
  return photo?.url || "";
}

export function uploadPropertyPhoto(propertyId, file, { isCover = false } = {}) {
  const form = new FormData();
  form.set("file", file);
  if (isCover) form.set("is_cover", "true");
  return mediaRequest(`/api/properties/${encodeURIComponent(propertyId)}/photos`, {
    method: "POST",
    body: form,
  });
}

export function uploadUnitPhoto(unitId, file, { roomId, isCover = false } = {}) {
  const form = new FormData();
  form.set("file", file);
  if (roomId) form.set("room_id", String(roomId));
  if (isCover) form.set("is_cover", "true");
  return mediaRequest(`/api/units/${encodeURIComponent(unitId)}/photos`, {
    method: "POST",
    body: form,
  });
}

export function setPhotoCover(photoId) {
  return mediaRequest(`/api/photos/${encodeURIComponent(photoId)}/cover`, {
    method: "PATCH",
  });
}

export function deletePhoto(photoId) {
  return mediaRequest(`/api/photos/${encodeURIComponent(photoId)}`, {
    method: "DELETE",
  });
}

export function reportListing(values) {
  return mediaRequest("/api/listing-reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}
