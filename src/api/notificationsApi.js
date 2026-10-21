import { request } from "./client";

export function listNotifications() {
  return request("/api/notifications").then((data) => data.notifications);
}

export function markNotificationRead(id) {
  return request(`/api/notifications/${encodeURIComponent(id)}/read`, {
    method: "PATCH",
  }).then((data) => data.notification);
}
