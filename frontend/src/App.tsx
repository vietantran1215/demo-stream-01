import { FormEvent, useEffect, useRef, useState } from "react";

import { resumeThread, sendMessage } from "./api";
import MarkdownContent from "./MarkdownContent";
import type {
  ApprovalRequest,
  Message,
  RouteName,
  StreamHandlers,
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
  const [nodes, setNodes] = useState<string[]>([]);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [approvalMessageId, setApprovalMessageId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  // Runtime decision trace for the latest prompt.
  const [activePrompt, setActivePrompt] = useState<string | null>(null);
  const [route, setRoute] = useState<RouteName | null>(null);
  const [expectedSkill, setExpectedSkill] = useState<string | null>(null);
  const [loadedSkill, setLoadedSkill] = useState<string | null>(null);
  const [skillSource, setSkillSource] = useState<string | null>(null);
  const [skillSkippedReason, setSkillSkippedReason] = useState<string | null>(null);
  const [trace, setTrace] = useState<string[]>([]);

  const messagesRef = useRef<HTMLElement | null>(null);
  const streamStartedRef = useRef(false);


  useEffect(() => {
    const element = messagesRef.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, approval]);


  function addTrace(entry: string): void {
    setTrace((current) =>
      current[current.length - 1] === entry ? current : [...current, entry],
    );
  }


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


  function messageLabel(message: Message): string {
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
        setStatus("Streaming model output");

        if (!streamStartedRef.current) {
          streamStartedRef.current = true;
          addTrace("Model stream started");
        }
      },
      onRoute: (selectedRoute, selectedSkill) => {
        setRoute(selectedRoute);
        setExpectedSkill(selectedSkill);
        setStatus(`Route selected: ${selectedRoute}`);
        addTrace(`Route selected: ${selectedRoute}`);

        if (selectedSkill) {
          addTrace(`Expected skill: ${selectedSkill}`);
        } else {
          addTrace("Expected skill: none");
        }
      },
      onSkill: (name, source) => {
        setLoadedSkill(name);
        setSkillSource(source);
        setSkillSkippedReason(null);
        setStatus(`Skill loaded: ${name}`);
        addTrace(`Skill loaded: ${name}`);
      },
      onSkillSkipped: (reason) => {
        setLoadedSkill(null);
        setSkillSource(null);
        setSkillSkippedReason(reason);
        addTrace("Skill skipped: not required");
      },
      onNode: (name) => {
        setNodes((current) => [...current, name]);
        addTrace(`Node completed: ${name}`);
      },
      onInterrupt: (request) => {
        setApproval(request);
        setApprovalMessageId(id);
        setStreamingMessageId(null);

        updateMessage(id, (message) => ({
          ...message,
          status: "draft_pending",
        }));

        setStatus("Waiting for human approval");
        addTrace("HITL: approval required");
      },
      onAction: (message) => {
        setStatus(message);
        addTrace(`Action: ${message}`);
      },
      onDone: (interrupted) => {
        setBusy(false);
        setStreamingMessageId(null);

        if (!interrupted) {
          // Normal general/summarize responses become final assistant messages.
          updateMessage(id, (message) =>
            message.status === "streaming"
              ? { ...message, status: "normal" }
              : message,
          );

          setStatus("Completed");
          addTrace("Completed");
        }
      },
      onError: (message) => {
        setError(message);
        setBusy(false);
        setStreamingMessageId(null);
        setStatus("Failed");
        addTrace(`Error: ${message}`);
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

    // Reset decision observability for this prompt only.
    setActivePrompt(message);
    setRoute(null);
    setExpectedSkill(null);
    setLoadedSkill(null);
    setSkillSource(null);
    setSkillSkippedReason(null);
    setTrace(["Prompt received"]);
    streamStartedRef.current = false;

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
      addTrace(`Error: ${message}`);
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
    setStatus(approved ? "Resuming: approved" : "Resuming: rejected");
    setApproval(null);
    addTrace(approved ? "Human decision: approved" : "Human decision: rejected");

    try {
      await resumeThread(
        threadId,
        approved,
        makeHandlers(`resume-${crypto.randomUUID()}`),
      );

      // Only mutate the visible draft after the backend resume completed
      // successfully. Approve means the send node ran; reject means the graph
      // terminated without executing the side effect.
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
      addTrace(`Error: ${message}`);
    }
  }


  function resetConversation(): void {
    setThreadId(newThreadId());
    setInput("");
    setMessages([]);
    setNodes([]);
    setApproval(null);
    setApprovalMessageId(null);
    setBusy(false);
    setError(null);
    setStreamingMessageId(null);
    setActivePrompt(null);
    setRoute(null);
    setExpectedSkill(null);
    setLoadedSkill(null);
    setSkillSource(null);
    setSkillSkippedReason(null);
    setTrace([]);
    streamStartedRef.current = false;
    setStatus("Ready");
  }


  const skillDisplay = !route
    ? "pending"
    : expectedSkill === null
      ? "none"
      : loadedSkill
        ? `${loadedSkill} ✓ loaded`
        : `${expectedSkill} … loading`;


  return (
    <main className="page-shell">
      <section className="app-card">
        <header className="app-header">
          <div>
            <p className="eyebrow">LANGGRAPH DEMO</p>
            <h1>Streaming + Router + Skills + HITL</h1>
            <p className="subtitle">
              Watch each prompt move through routing, skill selection, model streaming,
              and human approval in real time.
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
          <div>
            <span className="runtime-label">Route</span>
            <strong>{route ?? "—"}</strong>
          </div>
          <div>
            <span className="runtime-label">Skill</span>
            <strong>{route ? skillDisplay : "—"}</strong>
          </div>
        </section>

        <section className="decision-trace" aria-label="Prompt to skill trace">
          <div className="decision-header">
            <div>
              <p className="eyebrow">PROMPT → SKILL TRACE</p>
              <h2>Why this request uses this capability</h2>
            </div>
            {skillSource && <code className="skill-source">{skillSource}</code>}
          </div>

          {activePrompt ? (
            <>
              <div className="decision-flow">
                <div className="decision-step prompt-step">
                  <span className="runtime-label">Prompt</span>
                  <MarkdownContent content={activePrompt} />
                </div>

                <span className="decision-arrow">→</span>

                <div className="decision-step">
                  <span className="runtime-label">Route</span>
                  <strong>{route ?? "classifying…"}</strong>
                </div>

                <span className="decision-arrow">→</span>

                <div className="decision-step">
                  <span className="runtime-label">Skill</span>
                  <strong>{route ? skillDisplay : "waiting for route…"}</strong>
                  {skillSkippedReason && (
                    <small className="decision-note">{skillSkippedReason}</small>
                  )}
                </div>
              </div>

              <div className="trace-timeline">
                {trace.map((entry, index) => (
                  <div className="trace-entry" key={`${index}-${entry}`}>
                    <span className="trace-dot" />
                    <span>{entry}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="decision-empty">
              Send a prompt to see the router decision and actual skill-loading event.
            </p>
          )}
        </section>

        <section className="node-strip">
          <span className="runtime-label">Graph nodes</span>
          <span>{nodes.length ? nodes.join(" → ") : "—"}</span>
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
              <article
                key={message.id}
                className={`message ${message.role}`}
                data-status={message.status ?? "normal"}
              >
                <span className="message-role">{messageLabel(message)}</span>

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

            <p className="approval-review-note">
              Review the streamed draft above. Approve executes the fake send;
              Reject ends the graph without sending anything.
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
