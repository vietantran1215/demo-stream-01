import { FormEvent, useState } from "react";

import { resumeThread, sendMessage } from "./api";
import type { ApprovalRequest, Message, StreamHandlers } from "./types";


const EXAMPLES = [
  "What is LangGraph in one paragraph?",
  "Summarize this incident: The checkout API returned HTTP 503 from 09:31 to 10:04. A bad configuration was deployed at 09:27. Rollback completed at 10:02.",
  "Reply to the customer saying their refund has been approved and will arrive in 3-5 business days.",
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
      onToken: (content) => appendAssistantToken(id, content),
      onNode: (name) => {
        setNodes((current) => [...current, name]);
        setStatus(`Node: ${name}`);
      },
      onInterrupt: (request) => {
        setApproval(request);
        setStatus("Waiting for human approval");
      },
      onAction: (message) => setStatus(message),
      onDone: (interrupted) => {
        setBusy(false);
        if (!interrupted) {
          setStatus("Completed");
        }
      },
      onError: (message) => {
        setError(message);
        setBusy(false);
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
    setStatus("Running graph");
    setInput("");

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
    };
    setMessages((current) => [...current, userMessage]);

    const responseMessageId = `assistant-${crypto.randomUUID()}`;

    try {
      await sendMessage(threadId, message, makeHandlers(responseMessageId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
      setStatus("Failed");
    }
  }

  async function decide(approved: boolean): Promise<void> {
    if (!approval || busy) {
      return;
    }

    setBusy(true);
    setError(null);
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
              Minimal runtime demo. The backend owns workflow policy; this UI only
              renders stream events and human approval.
            </p>
          </div>
          <button className="secondary-button" onClick={resetConversation} disabled={busy}>
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

        <section className="messages" aria-live="polite">
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
                    {example}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <article key={message.id} className={`message ${message.role}`}>
                <span className="message-role">{message.role}</span>
                <div>{message.content || <span className="cursor">▌</span>}</div>
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
            <blockquote>{approval.draft}</blockquote>
            <div className="approval-actions">
              <button className="danger-button" onClick={() => decide(false)} disabled={busy}>
                Reject
              </button>
              <button className="primary-button" onClick={() => decide(true)} disabled={busy}>
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
            rows={3}
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
