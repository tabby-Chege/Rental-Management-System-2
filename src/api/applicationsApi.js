import { request } from "./client";

export function listApplications({ status } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const query = params.toString();
  return request(`/api/applications${query ? `?${query}` : ""}`).then(
    (data) => data.applications
  );
}

export function createApplication(values) {
  return request("/api/applications", {
    method: "POST",
    body: JSON.stringify(values),
  }).then((data) => data.application);
}

export function decideApplication(id, status) {
  return request(`/api/applications/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
