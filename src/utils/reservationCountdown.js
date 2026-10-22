export function formatReservationCountdown(deadline, now = Date.now()) {
  const deadlineTime = new Date(deadline).getTime();
  if (!Number.isFinite(deadlineTime)) return "Reservation deadline unavailable.";

  const remainingSeconds = Math.max(0, Math.floor((deadlineTime - now) / 1000));
  if (remainingSeconds === 0) {
    return "Deadline reached on this device; reservation status is confirmed by the server.";
  }

  const hours = Math.floor(remainingSeconds / 3600);
  const minutes = Math.floor((remainingSeconds % 3600) / 60);
  const seconds = remainingSeconds % 60;
  const formatted = [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
  return `Time remaining: ${formatted}`;
}
