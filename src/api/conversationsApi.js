import { request } from "./client.js";

export function listConversations() {
  return request("/api/conversations").then((data) => data.conversations);
}

export function startConversation(propertyId, body) {
  return request("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ property_id: propertyId, body }),
  });
}

export function listConversationMessages(conversationId) {
  return request(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages?per_page=100`,
  ).then((data) => data);
}

export function sendConversationMessage(conversationId, body) {
  return request(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ body }),
    },
  );
}
