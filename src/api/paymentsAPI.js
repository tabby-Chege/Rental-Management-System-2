import { request } from "./client.js";

export function listPayments({ page = 1, perPage = 10 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  return request(`/api/payments?${params.toString()}`);
}
export function createPayment(body) {
  return request("/api/payments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
