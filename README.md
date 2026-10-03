# demo-stream-01

Minimal end-to-end demo of **LangChain/LangGraph Streaming + Human-in-the-Loop (HITL) + FastAPI SSE + React**.

The project intentionally keeps only two execution paths so two different streaming levels and the HITL mechanics stay visible.

## Architecture

```text
User
  |
  v
Router
  |----------------------------------|
  |                                  |
  v                                  v
general                         support_agent
  |                             (create_agent)
  |                                  |
  v                                  v
model.astream()               agent model runtime
  |                                  |
  | explicit chunks                  | subgraph.messages
  v                                  v
get_stream_writer()             model tokens
  |                                  |
  |                                  v
  |                         LLM proposes @tool call
  |                                  |
  |                                  v
  |                       HumanInTheLoopMiddleware
  |                              [PAUSE]
  |                             /       \
  |                        Reject      Approve
  |                                      |
  |                                      v
  |                              send_support_reply
  |                                0→30→60→90→100
  |                                      |
  |                                      v
  |                               data/outbox.jsonl
  |
  +-------------------------+
                            |
                            v
                       FastAPI SSE
                            |
                            v
                          React
```

## Why two paths?

- `general` demonstrates **explicit model-level streaming** with `model.astream()`.
- `support_agent` demonstrates **graph/subgraph-level streaming** from a `create_agent` runtime, plus tool progress and HITL pause/resume.

The router exists only to make those two runtime behaviors easy to trigger in one small application.

## Stack

- Backend: Python 3.11+, FastAPI, LangChain 1.4.x, LangGraph 1.2.x, LangChain OpenAI
- Frontend: React 18, TypeScript, Vite
- Explicit model streaming: `model.astream()`
- Graph streaming: LangGraph Event Streaming v3
- Custom runtime events: `CustomTransformer` + `get_stream_writer()`
- Browser transport: Server-Sent Events over `fetch()`
- HITL: `HumanInTheLoopMiddleware` + `InMemorySaver`
- Demo side effect: `backend/data/outbox.jsonl`

> `InMemorySaver` is demo-only. Restarting the backend clears paused threads.

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

### General: explicit model streaming

```text
router
  -> general
  -> model.astream()
  -> AIMessageChunk
  -> get_stream_writer(model_token)
  -> run.custom
  -> FastAPI token SSE
  -> React
```

The node explicitly consumes the model stream:

```python
async for chunk in model.astream(messages, config):
    text = chunk_text(chunk)
    writer({
        "type": "model_token",
        "content": text,
        "source": "model_astream",
    })
```

It also accumulates the chunks and returns one final `AIMessage` so the graph state still contains a normal assistant response.

### Support reply: graph/subgraph streaming + HITL

```text
router
  -> support_agent
  -> create_agent internal model call
  -> subgraph.messages
  -> FastAPI token SSE
  -> model proposes send_support_reply(message=...)
  -> HumanInTheLoopMiddleware [PAUSE]
```

The application does not call `model.astream()` directly in this branch. Instead, LangGraph Event Streaming exposes the agent's model output through the nested subgraph's `messages` projection.

Approve executes the tool and streams progress. Reject skips the tool and returns rejection feedback to the agent.

## Two streaming levels

```text
1. Model-level streaming

model.astream()
    |
    v
AIMessageChunk
    |
    v
get_stream_writer()
    |
    v
run.custom


2. Graph-level streaming

create_agent()
    |
    v
nested LangGraph execution
    |
    v
subgraph.messages
```

Both are normalized into the same browser-facing SSE event:

```text
event: token
data: {"content":"...", "source":"..."}
```

The `source` value is:

- `model_astream` for the general path
- `subgraph_messages` for the support-agent path

This makes the difference observable and testable rather than conceptual only.

## SSE application protocol

Both chat endpoints return `text/event-stream`.

Events:

- `token`: user-facing text delta
- `route`: router decision
- `tool`: tool lifecycle/progress
- `interrupt`: HITL approval request
- `done`: stream finished or paused
- `error`: terminal application-level failure

FastAPI adapts both streaming mechanisms into this small browser-facing protocol. React does not need to know whether a token came from direct `model.astream()` or a LangGraph subgraph projection.

## Event Streaming v3

Event Streaming v3 registers `lifecycle`, `messages`, `subgraphs`, and `values` by default. This demo registers `CustomTransformer` because the explicit model stream and tool progress use `get_stream_writer()`, which surfaces through `run.custom` / `subgraph.custom`.

The async run-state API uses methods:

```python
interrupted = await run.interrupted()
interrupts = await run.interrupts()
```

## Core learning points

1. `model.astream()` gives application code direct control over model chunks.
2. A streaming node can still return one final `AIMessage` to normal LangGraph state.
3. `get_stream_writer()` lets explicit model chunks and runtime progress enter the graph event stream.
4. A `create_agent` runtime can be embedded as a subgraph node without manually streaming its model.
5. Nested-agent model output is observable through `subgraph.messages`.
6. Tool progress is a custom runtime stream, not model text.
7. `HumanInTheLoopMiddleware` pauses after the model proposes the tool call and before the side effect executes.
8. FastAPI normalizes model-level streaming, graph-level streaming, tool events, and interrupts into one SSE contract.

## Not production-grade

This demo deliberately uses an in-memory checkpointer and local JSONL side effect. Production systems still need durable persistence, authentication/thread ownership, idempotent tools, retries, cancellation, stream reconnection, observability, and deployment controls.
