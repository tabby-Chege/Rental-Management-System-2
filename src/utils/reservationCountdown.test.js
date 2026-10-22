import assert from "node:assert/strict";
import test from "node:test";

import { formatReservationCountdown } from "./reservationCountdown.js";

test("reservation countdown displays the server deadline as remaining time", () => {
  const now = Date.parse("2026-10-21T12:00:00.000Z");
  assert.equal(
    formatReservationCountdown("2026-10-21T13:00:00.000Z", now),
    "Time remaining: 01:00:00",
  );
  assert.equal(
    formatReservationCountdown("2026-10-21T12:59:59.000Z", now),
    "Time remaining: 00:59:59",
  );
});

test("reservation countdown never reports client-side expiry as authoritative", () => {
  assert.equal(
    formatReservationCountdown("2026-10-21T12:00:00.000Z", Date.parse("2026-10-21T12:00:01.000Z")),
    "Deadline reached on this device; reservation status is confirmed by the server.",
  );
  assert.equal(
    formatReservationCountdown("invalid"),
    "Reservation deadline unavailable.",
  );
});
