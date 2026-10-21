import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  listConversationMessages,
  listConversations,
  sendConversationMessage,
} from "../../api/conversationsApi";
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
  const [conversations, setConversations] = useState([]);
  const [activeConversation, setActiveConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

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
    if (!body || !activeId) return;
    setSending(true);
    setError("");
    try {
      const result = await sendConversationMessage(activeId, body);
      setMessages((current) => [...current, result.message]);
      setActiveConversation(result.conversation);
      setDraft("");
      setConversations((current) => [
        result.conversation,
        ...current.filter((item) => item.id !== result.conversation.id),
      ]);
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
                  <small>{conversation.latest_message?.body ?? "No messages yet"}</small>
                </button>
              ))
            )}
          </aside>
          <section className="messages-conversation" aria-label="Conversation">
            {activeId && String(activeConversation?.id) === activeId ? (
              <>
                <header className="messages-conversation-header">
                  <div>
                    <h2>{activeConversation.property?.name ?? "Property"}</h2>
                    <p>
                      {activeConversation.other_party?.name}
                      {activeConversation.property?.city
                        ? ` · ${activeConversation.property.city}`
                        : ""}
                    </p>
                  </div>
                  {activeConversation.property && (
                    <Link to={`/properties/${activeConversation.property.id}`}>
                      View listing
                    </Link>
                  )}
                </header>
                <ol className="messages-transcript" aria-live="polite">
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
                    />
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
