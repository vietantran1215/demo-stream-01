# demo-stream-01

Minimal end-to-end demo of **LangChain/LangGraph Streaming + Human-in-the-Loop (HITL) + FastAPI SSE + React**.

The project intentionally avoids RAG, skills, MCP, authentication, queues, databases, and cloud infrastructure so the runtime behavior stays visible.

## Architecture

```text
User
  |
  v
Router
  |-------------------------------|
  |               |               |
  v               v               v
general        summarize      support_agent
  |               |          (create_agent)
  |               |               |
  v               v               v
LLM stream      LLM stream    LLM proposes
                                @tool call
                                   |
                                   v
                        HumanInTheLoopMiddleware
                              [PAUSE]
                             /       \
                        Reject      Approve
                          |            |
                          |            v
                          |    send_support_reply
                          |      0→30→60→90→100
                          |            |
                          |            v
                          |     data/outbox.jsonl
                          |            |
                          +------> agent continues
```

## Stack

- Backend: Python 3.11+, FastAPI, LangChain 1.4.x, LangGraph 1.2.x, LangChain OpenAI
- Frontend: React 18, TypeScript, Vite
- Runtime streaming: LangGraph Event Streaming v3
- Custom runtime events: `CustomTransformer` + `get_stream_writer()`
- Browser transport: Server-Sent Events over `fetch()`
- HITL: `HumanInTheLoopMiddleware` + `InMemorySaver`
- Demo side effect: `backend/data/outbox.jsonl`

> `InMemorySaver` is demo-only. Restarting the backend clears paused threads.

## Repository layout

```text
.
├── backend
│   ├── app
│   │   ├── agent
│   │   │   ├── graph.py
│   │   │   ├── model.py
│   │   │   ├── nodes.py
│   │   │   ├── router.py
│   │   │   ├── state.py
│   │   │   └── support_agent.py
│   │   ├── main.py
│   │   └── schemas.py
│   ├── data/.gitkeep
│   ├── scripts/smoke.py
│   ├── dev.py
│   ├── .env.example
│   └── requirements.txt
└── frontend
    └── src
        ├── App.tsx
        ├── api.ts
        ├── MarkdownContent.tsx
        ├── styles.css
        └── types.ts
```

## Setup

Backend:

```bash
cd backend
python dev.py
```

Configure `backend/.env`:

```dotenv
OPENAI_API_KEY=<your-key-here>
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-6-luna
OPENAI_REASONING_EFFORT=none
FRONTEND_ORIGIN=http://localhost:5173
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Live smoke test:

```bash
cd backend
python scripts/smoke.py --live
```

## Runtime flow

### General

```text
router -> general -> END
```

### Summarize

```text
router -> summarize -> END
```

The summarize behavior is a small inline system prompt in `nodes.py`; there is no skill loader or external prompt file.

### Support reply + HITL

```text
router
  -> support_agent
  -> model proposes send_support_reply(message=...)
  -> HumanInTheLoopMiddleware [PAUSE]
```

Approve executes the tool and streams progress. Reject skips the tool and returns rejection feedback to the agent.

## SSE application protocol

Both chat endpoints return `text/event-stream`.

Events:

- `token`: user-facing model text delta
- `route`: router decision
- `tool`: tool lifecycle/progress
- `interrupt`: HITL approval request
- `done`: stream finished or paused
- `error`: terminal application-level failure

FastAPI is an adapter between LangGraph runtime events and this small browser-facing protocol. React does not know LangGraph or middleware payload shapes.

## Streaming details

Event Streaming v3 registers `lifecycle`, `messages`, `subgraphs`, and `values` by default. This demo registers `CustomTransformer` so `get_stream_writer()` tool progress and route events are available through `run.custom` and nested `subgraph.custom`.

The async API uses methods:

```python
interrupted = await run.interrupted()
interrupts = await run.interrupts()
```

The sync API exposes the equivalent state as properties.

## Core learning points

1. The parent LangGraph controls routing.
2. General and summarize are deterministic model nodes.
3. The support branch is a `create_agent` subgraph with a real LangChain `@tool`.
4. Native message projections stream model output without manually calling `model.astream()`.
5. Custom events stream long-running tool progress.
6. `HumanInTheLoopMiddleware` pauses after a tool call is proposed and before its side effect executes.
7. FastAPI normalizes LangGraph/HITL runtime structures into a framework-agnostic SSE contract.
8. React renders execution state instead of owning workflow policy.

## Not production-grade

This demo deliberately uses an in-memory checkpointer and local JSONL side effect. Production systems still need durable persistence, authentication/thread ownership, idempotent tools, retries, cancellation, stream reconnection, observability, and deployment controls.
