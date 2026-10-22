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

export function decideApplication(id, status, reason) {
  return request(`/api/applications/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ status, reason }),
  });
}

export function setApplicationLeaseTerms(id, leaseEndDate) {
  return request(
    `/api/applications/${encodeURIComponent(id)}/lease-terms`,
    {
      method: "PATCH",
      body: JSON.stringify({ lease_end_date: leaseEndDate }),
    },
  ).then((data) => data.application);
}

export function confirmReservationPayment(id, values) {
  return request(
    `/api/applications/${encodeURIComponent(id)}/confirm-payment`,
    {
      method: "POST",
      body: JSON.stringify(values),
    },
  );
}
