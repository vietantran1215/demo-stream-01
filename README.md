# demo-stream-01

Minimal end-to-end demo of **LangChain/LangGraph Streaming + Human-in-the-Loop (HITL) + FastAPI SSE + React**.

The project intentionally keeps only two execution paths so the streaming and HITL mechanics stay visible.

## Architecture

```text
User
  |
  v
Router
  |---------------------------|
  |                           |
  v                           v
general                  support_agent
  |                      (create_agent)
  v                           |
LLM stream                    v
  |                      LLM proposes
  v                         @tool call
 END                           |
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

## Why two paths?

- `general` demonstrates native model-output streaming from a normal LangGraph node.
- `support_agent` demonstrates nested-agent streaming, tool calling, custom tool-progress events, and HITL pause/resume.

The router exists only to make those two runtime behaviors easy to trigger in one small application.

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

## Runtime flows

### General

```text
router -> general -> model -> END
```

The node calls `model.ainvoke()`. LangGraph Event Streaming exposes the model deltas through the native message projection.

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

FastAPI adapts LangGraph runtime events into this small browser-facing protocol. React does not know LangGraph or middleware payload shapes.

## Streaming details

Event Streaming v3 registers `lifecycle`, `messages`, `subgraphs`, and `values` by default. This demo registers `CustomTransformer` so `get_stream_writer()` route and tool-progress events are available through `run.custom` and nested `subgraph.custom`.

The async run-state API uses methods:

```python
interrupted = await run.interrupted()
interrupts = await run.interrupts()
```

## Core learning points

1. A normal LangGraph node can call `model.ainvoke()` while its model output is still streamed through the message projection.
2. A `create_agent` runtime can be embedded as a subgraph node inside a parent LangGraph.
3. Nested agent model output and custom tool events must be consumed from the subgraph stream.
4. `get_stream_writer()` is useful for domain/runtime progress that is not model text.
5. `HumanInTheLoopMiddleware` pauses after the model proposes the tool call and before the side effect executes.
6. The same `thread_id` and checkpointer allow the paused execution to resume.
7. FastAPI normalizes framework-specific events into a small SSE contract.
8. React observes and controls runtime execution without owning workflow policy.

## Not production-grade

This demo deliberately uses an in-memory checkpointer and local JSONL side effect. Production systems still need durable persistence, authentication/thread ownership, idempotent tools, retries, cancellation, stream reconnection, observability, and deployment controls.
