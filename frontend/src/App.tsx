import { FormEvent, useEffect, useRef, useState } from "react";

import { resumeThread, sendMessage } from "./api";
import MarkdownContent from "./MarkdownContent";
import type {
  ApprovalRequest,
  Message,
  StreamHandlers,
  ToolEvent,
} from "./types";


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
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [approvalMessageId, setApprovalMessageId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  const messagesRef = useRef<HTMLElement | null>(null);


  useEffect(() => {
    const element = messagesRef.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, approval]);


  function updateMessage(
    id: string,
    updater: (message: Message) => Message,
  ): void {
    setMessages((current) =>
      current.map((message) =>
        message.id === id ? updater(message) : message,
      ),
    );
  }


  function appendAssistantToken(id: string, token: string): void {
    setMessages((current) => {
      const index = current.findIndex((message) => message.id === id);

      if (index === -1) {
        return [
          ...current,
          {
            id,
            role: "assistant",
            content: token,
            status: "streaming",
          },
        ];
      }

      return current.map((message) =>
        message.id === id
          ? {
              ...message,
              content: message.content + token,
              status: "streaming",
            }
          : message,
      );
    });
  }


  function insertSkillEventBefore(responseId: string, skillName: string): void {
    setMessages((current) => {
      const eventId = `skill-${responseId}-${skillName}`;

      if (current.some((message) => message.id === eventId)) {
        return current;
      }

      const responseIndex = current.findIndex((message) => message.id === responseId);
      const skillMessage: Message = {
        id: eventId,
        role: "system",
        content: `Skill active: ${skillName}`,
        status: "normal",
      };

      if (responseIndex === -1) {
        return [...current, skillMessage];
      }

      return [
        ...current.slice(0, responseIndex),
        skillMessage,
        ...current.slice(responseIndex),
      ];
    });
  }


  function upsertToolEvent(requestId: string, event: ToolEvent): void {
    const toolMessageId = `tool-${requestId}-${event.tool}`;

    setMessages((current) => {
      const existing = current.find((message) => message.id === toolMessageId);

      if (!existing) {
        return [
          ...current,
          {
            id: toolMessageId,
            role: "tool",
            content: event.message,
            status: "normal",
            toolName: event.tool,
            toolProgress: event.progress,
            toolState: event.phase,
          },
        ];
      }

      return current.map((message) =>
        message.id === toolMessageId
          ? {
              ...message,
              content: event.message,
              toolName: event.tool,
              toolProgress: event.progress,
              toolState: event.phase,
            }
          : message,
      );
    });
  }


  function messageLabel(message: Message): string {
    if (message.role === "system") {
      return "RUNTIME";
    }

    if (message.role === "tool") {
      return message.toolState === "completed"
        ? "TOOL · COMPLETED"
        : "TOOL · RUNNING";
    }

    if (message.role !== "assistant") {
      return message.role;
    }

    switch (message.status) {
      case "draft_pending":
        return "DRAFT · PENDING APPROVAL";
      case "approved_sent":
        return "ASSISTANT · APPROVED & SENT";
      case "rejected":
        return "DRAFT · REJECTED · NOT SENT";
      default:
        return "ASSISTANT";
    }
  }


  function makeHandlers(id: string): StreamHandlers {
    return {
      onToken: (content) => {
        appendAssistantToken(id, content);
        setStreamingMessageId(id);
        setStatus("Streaming");
      },
      onRoute: () => {
        setStatus("Route selected");
      },
      onSkill: (name) => {
        // Show only skills that were actually loaded by the backend.
        // Put the event before the response bubble so the causal order is clear.
        insertSkillEventBefore(id, name);
        setStatus(`Skill: ${name}`);
      },
      onSkillSkipped: () => {
        // General requests intentionally have no skill event in the conversation.
      },
      onTool: (event) => {
        upsertToolEvent(id, event);
        setStatus(`Tool: ${event.tool} · ${event.progress}%`);
      },
      onInterrupt: (request) => {
        setApproval(request);
        setApprovalMessageId(id);
        setStreamingMessageId(null);

        updateMessage(id, (message) => ({
          ...message,
          // The middleware interrupt exposes the exact tool arguments under
          // review. Show that payload because it is what approval will execute.
          content: request.draft || message.content,
          status: "draft_pending",
        }));

        setStatus("Waiting for approval");
      },
      onDone: (interrupted) => {
        setBusy(false);
        setStreamingMessageId(null);

        if (!interrupted) {
          updateMessage(id, (message) =>
            message.status === "streaming"
              ? { ...message, status: "normal" }
              : message,
          );

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
    setBusy(true);
    setStatus("Routing");
    setInput("");

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
    };

    const responseMessageId = `assistant-${crypto.randomUUID()}`;

    setMessages((current) => [
      ...current,
      userMessage,
      {
        id: responseMessageId,
        role: "assistant",
        content: "",
        status: "streaming",
      },
    ]);
    setStreamingMessageId(responseMessageId);

    try {
      await sendMessage(threadId, message, makeHandlers(responseMessageId));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      setError(message);
      setBusy(false);
      setStreamingMessageId(null);
      setStatus("Failed");
    }
  }


  async function decide(approved: boolean): Promise<void> {
    if (!approval || !approvalMessageId || busy) {
      return;
    }

    const draftMessageId = approvalMessageId;

    setBusy(true);
    setError(null);
    setStreamingMessageId(null);
    setStatus(approved ? "Approving…" : "Rejecting…");
    setApproval(null);

    try {
      await resumeThread(
        threadId,
        approved,
        makeHandlers(`resume-${crypto.randomUUID()}`),
      );

      updateMessage(draftMessageId, (message) => ({
        ...message,
        status: approved ? "approved_sent" : "rejected",
      }));

      setApprovalMessageId(null);
      setStatus(approved ? "Approved and sent" : "Rejected — not sent");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      setError(message);
      setBusy(false);
      setStreamingMessageId(null);
      setStatus("Failed");
    }
  }


  function resetConversation(): void {
    setThreadId(newThreadId());
    setInput("");
    setMessages([]);
    setApproval(null);
    setApprovalMessageId(null);
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
              Skills appear inline only when the backend actually loads them.
            </p>
          </div>

          <div className="header-actions">
            <span className="status-pill">{status}</span>
            <button
              className="secondary-button"
              onClick={resetConversation}
              disabled={busy}
            >
              New thread
            </button>
          </div>
        </header>

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
              <article
                key={message.id}
                className={`message ${message.role}`}
                data-status={message.status ?? "normal"}
                data-tool-state={message.toolState ?? ""}
              >
                <span className="message-role">{messageLabel(message)}</span>

                {message.role === "system" ? (
                  <span className="skill-event-text">{message.content}</span>
                ) : message.role === "tool" ? (
                  <div className="tool-event">
                    <div className="tool-event-row">
                      <code>{message.toolName ?? "tool"}</code>
                      <strong>{message.toolProgress ?? 0}%</strong>
                    </div>
                    <div className="tool-progress-track" aria-hidden="true">
                      <div
                        className="tool-progress-value"
                        style={{ width: `${message.toolProgress ?? 0}%` }}
                      />
                    </div>
                    <span className="tool-event-copy">{message.content}</span>
                  </div>
                ) : message.content ? (
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

            <p className="approval-review-note">
              Review the proposed draft above. Approve executes the fake send;
              Reject skips the tool and returns feedback to the agent.
            </p>

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
