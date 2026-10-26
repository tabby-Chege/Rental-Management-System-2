import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  listConversationMessages,
  listConversations,
  startConversation,
  sendConversationMessage,
} from "../../api/conversationsApi";
import { listProperties } from "../../api/propertiesApi";
import "../manage.css";
import "./MessagesPage.css";

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function MessagesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeId = searchParams.get("conversation");
  const targetTenantId = searchParams.get("tenant_user_id");
  const requestedPropertyId = searchParams.get("property_id");
  const requestedUnitId = searchParams.get("unit_id");
  const requestedApplicationId = searchParams.get("application_id");
  const [conversations, setConversations] = useState([]);
  const [properties, setProperties] = useState([]);
  const selectionKey = `${targetTenantId ?? ""}:${requestedPropertyId ?? ""}`;
  const [propertySelection, setPropertySelection] = useState({ key: "", value: "" });
  const selectedPropertyId = propertySelection.key === selectionKey
    ? propertySelection.value
    : requestedPropertyId ?? "";
  const [activeConversation, setActiveConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const transcriptRef = useRef(null);
  const lastScrolledMessageId = useRef(null);
  const isStartingConversation = Boolean(targetTenantId && !activeId);
  const latestMessageId = messages.at(-1)?.id ?? null;

  useEffect(() => {
    if (!isStartingConversation) return undefined;
    let ignore = false;
    listProperties({ page: 1, perPage: 100 })
      .then((result) => {
        if (!ignore) setProperties(result.properties ?? []);
      })
      .catch((requestError) => {
        if (!ignore) setError(requestError.message);
      });
    return () => {
      ignore = true;
    };
  }, [isStartingConversation]);

  useEffect(() => {
    if (!latestMessageId || lastScrolledMessageId.current === latestMessageId) return;
    lastScrolledMessageId.current = latestMessageId;
    const transcript = transcriptRef.current;
    if (transcript) {
      transcript.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
    }
  }, [latestMessageId]);

  useEffect(() => {
    let ignore = false;
    async function loadConversations() {
      try {
        const result = await listConversations();
        if (!ignore) {
          setConversations(result);
          setError("");
        }
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    loadConversations();
    const interval = window.setInterval(loadConversations, 15000);
    return () => {
      ignore = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!activeId) return undefined;

    let ignore = false;
    async function loadMessages() {
      try {
        const result = await listConversationMessages(activeId);
        if (!ignore) {
          setActiveConversation(result.conversation);
          setMessages(result.messages);
          setError("");
          listConversations().then(setConversations).catch((requestError) => {
            if (!ignore) setError(requestError.message);
          });
        }
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      }
    }
    loadMessages();
    const interval = window.setInterval(loadMessages, 10000);
    return () => {
      ignore = true;
      window.clearInterval(interval);
    };
  }, [activeId]);

  async function handleSend(event) {
    event.preventDefault();
    const body = draft.trim();
    if (!body || (!activeId && !isStartingConversation)) return;
    if (isStartingConversation && !selectedPropertyId) {
      setError("Choose a property for this conversation.");
      return;
    }
    setSending(true);
    setError("");
    try {
      const result = isStartingConversation
        ? await startConversation(
            Number(selectedPropertyId),
            body,
            {
              tenant_user_id: Number(targetTenantId),
              ...(requestedPropertyId === selectedPropertyId && requestedUnitId
                ? { unit_id: Number(requestedUnitId) }
                : {}),
              ...(requestedPropertyId === selectedPropertyId && requestedApplicationId
                ? { application_id: Number(requestedApplicationId) }
                : {}),
            },
          )
        : await sendConversationMessage(activeId, body);
      setMessages((current) =>
        isStartingConversation ? [result.message] : [...current, result.message],
      );
      setActiveConversation(result.conversation);
      setDraft("");
      setConversations((current) => [
        result.conversation,
        ...current.filter((item) => item.id !== result.conversation.id),
      ]);
      if (isStartingConversation) {
        setSearchParams({ conversation: String(result.conversation.id) });
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="manage-page messages-page">
      <header>
        <h1>Messages</h1>
        <p className="manage-status">
          Discuss a property privately with its landlord before or after applying.
        </p>
      </header>
      {error && <p className="manage-error" role="alert">{error}</p>}
      {loading ? (
        <p className="manage-status">Loading conversations…</p>
      ) : (
        <div className="messages-layout">
          <aside className="messages-inbox" aria-label="Conversations">
            {conversations.length === 0 ? (
              <p className="manage-status">No property conversations yet.</p>
            ) : (
              conversations.map((conversation) => (
                <button
                  className={`messages-thread${String(conversation.id) === activeId ? " is-active" : ""}`}
                  type="button"
                  key={conversation.id}
                  aria-current={String(conversation.id) === activeId ? "page" : undefined}
                  onClick={() =>
                    setSearchParams({ conversation: String(conversation.id) })
                  }
                >
                  <strong>{conversation.property?.name ?? "Property"}</strong>
                  <span>
                    {conversation.other_party?.name ?? "Participant"} ·{" "}
                    {conversation.property?.city}
                  </span>
                  <small>
                    {conversation.unread_count > 0 && (
                      <b>{conversation.unread_count} unread · </b>
                    )}
                    {conversation.latest_message?.body ?? "No messages yet"}
                  </small>
                  {conversation.latest_message?.created_at && (
                    <time dateTime={conversation.latest_message.created_at}>
                      {formatDate(conversation.latest_message.created_at)}
                    </time>
                  )}
                </button>
              ))
            )}
          </aside>
          <section className={`messages-conversation${isStartingConversation ? " is-starting" : ""}`} aria-label="Conversation">
            {isStartingConversation ? (
              <>
                <header className="messages-conversation-header">
                  <div>
                    <h2>New conversation</h2>
                    <p>Send a private message to this tenant.</p>
                  </div>
                </header>
                <div className="messages-start-context">
                  <label className="manage-field">
                    <span>Property</span>
                    <select
                      value={selectedPropertyId}
                      disabled={Boolean(requestedApplicationId)}
                      required
                      onChange={(event) => setPropertySelection({
                        key: selectionKey,
                        value: event.target.value,
                      })}
                    >
                      <option value="">Choose a property</option>
                      {properties.map((property) => (
                        <option key={property.id} value={property.id}>{property.name} · {property.city}</option>
                      ))}
                    </select>
                  </label>
                  {requestedUnitId && (
                    <p>Unit context: {properties.find((property) => String(property.id) === selectedPropertyId)?.name ?? "Selected property"} · Unit #{requestedUnitId}</p>
                  )}
                </div>
                <form className="messages-compose" onSubmit={handleSend}>
                  <label className="manage-field">
                    <span>Write your first message</span>
                    <textarea
                      value={draft}
                      maxLength={5000}
                      rows={3}
                      required
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                          event.preventDefault();
                          event.currentTarget.form?.requestSubmit();
                        }
                      }}
                    />
                    <small>Press Enter to send · Shift+Enter for a new line</small>
                  </label>
                  <button className="manage-button" type="submit" disabled={sending || !draft.trim()}>
                    {sending ? "Sending…" : "Send message"}
                  </button>
                </form>
              </>
            ) : activeId && String(activeConversation?.id) === activeId ? (
              <>
                <header className="messages-conversation-header">
                  <div>
                    <h2>{activeConversation.property?.name ?? "Property"}</h2>
                    <p>
                      {activeConversation.other_party?.name}
                      {activeConversation.property?.city
                        ? ` · ${activeConversation.property.city}`
                        : ""}
                      {activeConversation.unit
                        ? ` · Unit ${activeConversation.unit.unit_number}`
                        : ""}
                      {activeConversation.application_id
                        ? ` · Application #${activeConversation.application_id}`
                        : ""}
                      {activeConversation.lease_id
                        ? ` · Lease #${activeConversation.lease_id}`
                        : ""}
                    </p>
                  </div>
                  {activeConversation.property && (
                    <Link to={`/properties/${activeConversation.property.id}`}>
                      View listing
                    </Link>
                  )}
                </header>
                <ol className="messages-transcript" aria-live="polite" ref={transcriptRef}>
                  {messages.map((message) => (
                    <li
                      className={
                        message.sender_user_id === activeConversation.other_party?.id
                          ? "messages-bubble is-incoming"
                          : "messages-bubble is-outgoing"
                      }
                      key={message.id}
                    >
                      <p>{message.body}</p>
                      <time dateTime={message.created_at}>
                        {formatDate(message.created_at)}
                      </time>
                    </li>
                  ))}
                </ol>
                <form className="messages-compose" onSubmit={handleSend}>
                  <label className="manage-field">
                    <span>Write a message</span>
                    <textarea
                      value={draft}
                      maxLength={5000}
                      rows={3}
                      required
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (
                          event.key === "Enter" &&
                          !event.shiftKey &&
                          !event.nativeEvent.isComposing
                        ) {
                          event.preventDefault();
                          event.currentTarget.form?.requestSubmit();
                        }
                      }}
                    />
                    <small>Press Enter to send · Shift+Enter for a new line</small>
                  </label>
                  <button
                    className="manage-button"
                    type="submit"
                    disabled={sending || !draft.trim()}
                  >
                    {sending ? "Sending…" : "Send message"}
                  </button>
                </form>
              </>
            ) : (
              <div className="messages-empty">
                <h2>Select a conversation</h2>
                <p>Choose a property conversation to read and reply.</p>
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

export default MessagesPage;
