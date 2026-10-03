import { FormEvent, useEffect, useRef, useState } from "react";

import { resumeThread, sendMessage } from "./api";
import MarkdownContent from "./MarkdownContent";
import type { ApprovalRequest, Message, StreamHandlers } from "./types";


const EXAMPLES = [
  "What is **LangGraph** in one paragraph?",
  "Summarize this incident:\n\n- Checkout API returned **HTTP 503** from 09:31 to 10:04.\n- A bad configuration was deployed at 09:27.\n- Rollback completed at 10:02.",
  "Reply to the customer saying their refund has been **approved** and will arrive in `3-5 business days`.",
];


function newThreadId(): string {
  return crypto.randomUUID();
}


export default function App() {
  const [threadId, setThreadId] = useState(newThreadId);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [nodes, setNodes] = useState<string[]>([]);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  const messagesRef = useRef<HTMLElement | null>(null);


  // Keep the newest streamed token visible without requiring manual scrolling.
  useEffect(() => {
    const element = messagesRef.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, approval]);


  function appendAssistantToken(id: string, token: string): void {
    setMessages((current) => {
      const index = current.findIndex((message) => message.id === id);

      if (index === -1) {
        return [...current, { id, role: "assistant", content: token }];
      }

      return current.map((message) =>
        message.id === id
          ? { ...message, content: message.content + token }
          : message,
      );
    });
  }


  function makeHandlers(id: string): StreamHandlers {
    return {
      onToken: (content) => {
        // Every SSE token updates React state immediately.
        // MarkdownContent reparses the growing string on every render.
        appendAssistantToken(id, content);
        setStreamingMessageId(id);
        setStatus("Streaming model output");
      },
      onNode: (name) => {
        setNodes((current) => [...current, name]);
        setStatus(`Node: ${name}`);
      },
      onInterrupt: (request) => {
        setApproval(request);
        setStreamingMessageId(null);
        setStatus("Waiting for human approval");
      },
      onAction: (message) => setStatus(message),
      onDone: (interrupted) => {
        setBusy(false);
        setStreamingMessageId(null);

        if (!interrupted) {
          setStatus("Completed");
        }
      },
      onError: (message) => {
        setError(message);
        setBusy(false);
        setStreamingMessageId(null);
        setStatus("Failed");
      },
    };
  }


  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    const message = input.trim();

    if (!message || busy || approval) {
      return;
    }

    setError(null);
    setNodes([]);
    setBusy(true);
    setStatus("Routing request");
    setInput("");

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
    };

    const responseMessageId = `assistant-${crypto.randomUUID()}`;

    // Create the assistant bubble before the first network chunk arrives.
    // This makes the streaming lifecycle visible immediately via the cursor.
    setMessages((current) => [
      ...current,
      userMessage,
      {
        id: responseMessageId,
        role: "assistant",
        content: "",
      },
    ]);
    setStreamingMessageId(responseMessageId);

    try {
      await sendMessage(threadId, message, makeHandlers(responseMessageId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
      setStreamingMessageId(null);
      setStatus("Failed");
    }
  }


  async function decide(approved: boolean): Promise<void> {
    if (!approval || busy) {
      return;
    }

    setBusy(true);
    setError(null);
    setStreamingMessageId(null);
    setStatus(approved ? "Resuming: approved" : "Resuming: rejected");
    setApproval(null);

    try {
      await resumeThread(
        threadId,
        approved,
        makeHandlers(`resume-${crypto.randomUUID()}`),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
      setStreamingMessageId(null);
      setStatus("Failed");
    }
  }


  function resetConversation(): void {
    setThreadId(newThreadId());
    setInput("");
    setMessages([]);
    setNodes([]);
    setApproval(null);
    setBusy(false);
    setError(null);
    setStreamingMessageId(null);
    setStatus("Ready");
  }


  return (
    <main className="page-shell">
      <section className="app-card">
        <header className="app-header">
          <div>
            <p className="eyebrow">LANGGRAPH DEMO</p>
            <h1>Streaming + Router + Skills + HITL</h1>
            <p className="subtitle">
              Token-by-token output with live Markdown rendering. The backend owns
              workflow policy; this UI only renders stream events and human approval.
            </p>
          </div>
          <button
            className="secondary-button"
            onClick={resetConversation}
            disabled={busy}
          >
            New thread
          </button>
        </header>

        <section className="runtime-strip" aria-label="Runtime state">
          <div>
            <span className="runtime-label">Thread</span>
            <code>{threadId.slice(0, 8)}</code>
          </div>
          <div>
            <span className="runtime-label">Status</span>
            <strong>{status}</strong>
          </div>
          <div className="node-list">
            <span className="runtime-label">Nodes</span>
            <span>{nodes.length ? nodes.join(" → ") : "—"}</span>
          </div>
        </section>

        <section className="messages" aria-live="polite" ref={messagesRef}>
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>Try one of the three paths</h2>
              <div className="example-grid">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    className="example-card"
                    onClick={() => setInput(example)}
                    disabled={busy || Boolean(approval)}
                  >
                    <MarkdownContent content={example} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <article key={message.id} className={`message ${message.role}`}>
                <span className="message-role">{message.role}</span>

                {message.content ? (
                  <MarkdownContent content={message.content} />
                ) : null}

                {streamingMessageId === message.id ? (
                  <span className="cursor" aria-label="Streaming">
                    ▌
                  </span>
                ) : null}
              </article>
            ))
          )}
        </section>

        {approval && (
          <section className="approval-card">
            <div>
              <p className="eyebrow">HUMAN-IN-THE-LOOP</p>
              <h2>Approval required</h2>
              <p className="approval-copy">
                The graph is paused. No side effect has executed yet.
              </p>
            </div>

            <div className="approval-draft">
              <MarkdownContent content={approval.draft} />
            </div>

            <div className="approval-actions">
              <button
                className="danger-button"
                onClick={() => decide(false)}
                disabled={busy}
              >
                Reject
              </button>
              <button
                className="primary-button"
                onClick={() => decide(true)}
                disabled={busy}
              >
                Approve & fake send
              </button>
            </div>
          </section>
        )}

        {error && <div className="error-banner">{error}</div>}

        <form className="composer" onSubmit={submit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask a question, summarize content, or draft a support reply..."
            rows={4}
            disabled={busy || Boolean(approval)}
          />
          <button
            className="primary-button"
            type="submit"
            disabled={busy || Boolean(approval) || !input.trim()}
          >
            {busy ? "Running..." : "Send"}
          </button>
        </form>
      </section>
    </main>
  );
}
