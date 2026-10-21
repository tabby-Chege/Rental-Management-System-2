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

export function listPaymentProviders() {
  return request("/api/payments/providers").then((data) => data.providers);
}

export function startPaymentCheckout(values) {
  return request("/api/payments/checkout", {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(values),
  }).then((data) => data.attempt);
}

export function getPaymentAttempt(id) {
  return request(`/api/payments/attempts/${encodeURIComponent(id)}`).then(
    (data) => data.attempt,
  );
}

export function listPaymentAttempts({ status } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const query = params.toString();
  return request(`/api/payments/attempts${query ? `?${query}` : ""}`).then(
    (data) => data.attempts,
  );
}

export function confirmBankTransfer(id, providerReference) {
  return request(`/api/payments/attempts/${encodeURIComponent(id)}/confirm`, {
    method: "POST",
    body: JSON.stringify({ provider_reference: providerReference }),
  }).then((data) => data.attempt);
}

export function listRentInvoices({ page = 1, perPage = 50 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  return request(`/api/payments/invoices?${params.toString()}`).then(
    (data) => data.invoices,
  );
}

export function getDepositLedger(leaseId) {
  const params = new URLSearchParams();
  if (leaseId) params.set("lease_id", String(leaseId));
  const query = params.toString();
  return request(`/api/payments/deposits${query ? `?${query}` : ""}`);
}

export function createDepositLedgerEntry(body) {
  return request("/api/payments/deposits", {
    method: "POST",
    body: JSON.stringify(body),
  }).then((data) => data.entry);
}
