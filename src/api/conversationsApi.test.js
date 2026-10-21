import assert from "node:assert/strict";
import test from "node:test";

import {
  listConversationMessages,
  startConversation,
} from "./conversationsApi.js";

test("property questions start an authenticated conversation", async () => {
  globalThis.localStorage = {
    getItem: (key) => key === "access_token" ? "access" : null,
    removeItem: () => {},
    setItem: () => {},
  };
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({
      conversation: { id: 12 },
      message: { body: "Is parking available?" },
    }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await startConversation(4, "Is parking available?");

  assert.equal(result.conversation.id, 12);
  assert.equal(calls[0].url, "/api/conversations");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    property_id: 4,
    body: "Is parking available?",
  });
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("conversation message history requests a larger page", async () => {
  globalThis.localStorage = {
    getItem: (key) => key === "access_token" ? "access" : null,
    removeItem: () => {},
    setItem: () => {},
  };
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return new Response(JSON.stringify({
      conversation: { id: 12 },
      messages: [],
      pagination: { total: 0 },
    }), { headers: { "Content-Type": "application/json" } });
  };

  await listConversationMessages(12);

  assert.equal(requestedUrl, "/api/conversations/12/messages?per_page=100");
  delete globalThis.localStorage;
  delete globalThis.fetch;
});
