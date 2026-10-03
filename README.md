# demo-stream-01

Minimal end-to-end demo of **LangGraph routing + LangChain create_agent + Skills + Event Streaming + Human-in-the-Loop (HITL) middleware + React UI**.

The project intentionally avoids RAG, databases, MCP, authentication, queues, and cloud infrastructure so the runtime behavior stays visible.

## What this demo teaches

```text
User
  |
  v
Router
  |---------------------------|
  |                           |
  v                           v
general                   summarize
  |                           |
  |                      load SKILL.md
  |                           |
  v                           v
LLM streaming            LLM streaming
  |                           |
  v                           v
 END                         END

Router
  |
  v
support_skill
  |
  v
support_agent (create_agent)
  |
  v
LLM proposes send_support_reply(...)
  |
  v
HumanInTheLoopMiddleware [PAUSE]
  |
  +---- Reject ----> feedback to agent
  |
  +---- Approve ---> send_support_reply @tool
                          |
                          v
                    0→30→60→90→100
                          |
                          v
                 data/outbox.jsonl
                          |
                          v
                    agent confirms
```

## Stack

- Backend: Python 3.11+, FastAPI, LangChain 1.4.x, LangGraph 1.2.x, LangChain OpenAI
- Frontend: React 18, TypeScript, Vite
- Graph streaming: LangGraph Event Streaming v3 (`messages`, interrupts) + opt-in `CustomTransformer` for `get_stream_writer()` events
- Browser transport: Server-Sent Events over `fetch()`
- HITL persistence for the demo: LangGraph `InMemorySaver`
- Side effect: local `backend/data/outbox.jsonl`

> `InMemorySaver` is intentionally demo-only. Restarting the backend clears paused threads.

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
│   │   ├── skills
│   │   │   ├── loader.py
│   │   │   ├── summarize/SKILL.md
│   │   │   └── support-reply/SKILL.md
│   │   ├── main.py
│   │   └── schemas.py
│   ├── data/.gitkeep
│   ├── scripts/smoke.py
│   ├── dev.py
│   ├── .env.example
│   └── requirements.txt
└── frontend
    ├── src
    │   ├── App.tsx
    │   ├── api.ts
    │   ├── main.tsx
    │   ├── styles.css
    │   └── types.ts
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    └── vite.config.ts
```

## 1. Backend setup

### Recommended: one command

`dev.py` uses only the Python standard library. It creates `.venv` when missing, installs dependencies into that exact interpreter, creates `.env` from the example when needed, and starts Uvicorn through the venv Python.

```bash
cd backend
python dev.py
```

This deliberately does **not** depend on shell activation, so a globally installed `uvicorn` cannot accidentally run the app with the wrong Python environment.

Configure `backend/.env` before using model-backed routes:

```dotenv
OPENAI_API_KEY=<your-key-here>
OPENAI_BASE_URL=<your-base-url-here>
OPENAI_MODEL=gpt-6-luna
OPENAI_REASONING_EFFORT=none
FRONTEND_ORIGIN=http://localhost:5173
```

### Manual setup

If you want to see every environment step explicitly:

```bash
cd backend

python -m venv .venv
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

# Use "python -m pip", not bare "pip", so installation and runtime
# use the exact same Python interpreter.
python -m pip install -r requirements.txt

cp .env.example .env

# Same rule for Uvicorn: run it as a module through the active Python.
python -m uvicorn app.main:app --reload --port 8000
```

Sanity check:

```bash
which python
python -c "import sys, fastapi; print(sys.executable); print(fastapi.__version__)"
```

On macOS/Linux, `sys.executable` should point inside `backend/.venv/bin/python`.

If a traceback instead points to a global path such as `/Library/Frameworks/Python.framework/...`, the wrong interpreter is running. Use `python dev.py` or reactivate `.venv`.

Health check:

```bash
curl http://localhost:8000/health
```

## 2. Frontend setup

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

The frontend defaults to `http://localhost:8000`. To override it:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## 3. Demo scenarios

### General route

```text
What is LangGraph in one paragraph?
```

Expected graph:

```text
router -> general -> END
```

### Summarize skill

```text
Summarize this incident:

The checkout API returned HTTP 503 from 09:31 to 10:04.
A bad configuration was deployed at 09:27.
Rollback completed at 10:02.
Some payments were retried successfully.
```

Expected graph:

```text
router -> summarize -> END
```

The `summarize/SKILL.md` file is loaded only after the router selects that capability.

### Support reply + approve

```text
Reply to the customer saying their refund has been approved and will arrive in 3-5 business days.
```

Expected graph:

```text
router
  -> support_skill
  -> support_agent
  -> LLM proposes send_support_reply(...)
  -> HumanInTheLoopMiddleware [PAUSE]
                                  |
                               approve
                                  |
                                  v
                         send_support_reply @tool
                                  |
                                  v
                             agent confirms
```

The middleware interrupt contains the exact proposed tool arguments, so the UI shows the message that approval would execute. Click **Approve**. The fake tool streams progress and appends one JSON line to:

```text
backend/data/outbox.jsonl
```

### Support reply + reject

Use the same prompt, then click **Reject**.

Expected:

```text
HumanInTheLoopMiddleware [PAUSE]
          |
        reject
          |
          v
tool call skipped
          |
          v
rejection feedback returned to support_agent
```

No outbox record is written. The agent is explicitly instructed not to retry the rejected send unless the user asks again.

## Smoke test

With the backend running:

```bash
cd backend
python scripts/smoke.py
```

The script checks the health endpoint and prints the exact manual scenarios to run. Use:

```bash
python scripts/smoke.py --live
```

to execute the model-backed routes, verify skill activation, pause/resume the built-in HITL middleware, and assert the streamed tool progress sequence `0 → 30 → 60 → 90 → 100`.

## API protocol

### Start / continue a conversation

```http
POST /api/chat/{thread_id}
Content-Type: application/json

{
  "message": "Reply to the customer..."
}
```

### Resume an interrupted graph

```http
POST /api/chat/{thread_id}/resume
Content-Type: application/json

{
  "approved": true
}
```

Both endpoints stream SSE events.

Event types:

- `token`: user-facing LLM text delta from the native message projection
- `route`: router decision metadata
- `skill`: a skill was actually loaded
- `skill_skipped`: the selected route does not need a skill
- `tool`: long-running tool lifecycle/progress
- `interrupt`: graph is paused and requires human input
- `done`: request stream is complete
- `error`: terminal application-level stream error

The backend uses LangGraph Event Streaming v3 as the runtime-facing API and adapts its typed projections to this intentionally small SSE contract. Root projections carry the deterministic branches; the support agent runs as a nested subgraph, so its messages and custom tool-progress events are consumed from the subgraph projection. The frontend does not know LangGraph or middleware internals; it only renders these application events.

> LangGraph 1.2.x currently marks Event Streaming v3 as experimental. This demo uses it because it is the current recommended direction for new applications, while keeping the browser protocol small enough to swap the backend streaming adapter later if the API changes.

## Core learning points

1. **Router is not an agent.** The parent graph deterministically selects a branch.
2. **A graph can contain an agentic subgraph.** Only the support branch uses `create_agent`; general and summarize remain deterministic.
3. **Skills still scope behavior.** The summarize branch loads its skill directly; the support skill becomes the support agent's system instructions.
4. **Native message projections stream model output.** Root model calls and nested support-agent model calls are consumed from their correct Event Streaming scopes.
5. **Custom events carry domain progress.** Skill activation and long-running tool progress use `get_stream_writer()`; Event Streaming v3 requires explicitly registering `CustomTransformer` before `run.custom` / `subgraph.custom` exist.
6. **The side effect is now a real tool.** `send_support_reply` is a LangChain `@tool`, not a graph node pretending to be one.
7. **Built-in HITL governs the risky tool call.** `HumanInTheLoopMiddleware` pauses after the model proposes the tool but before execution.
8. **Approve/reject are middleware decisions.** Approve executes the original tool call; reject skips it and returns feedback to the agent.
9. **Frontend stays framework-agnostic.** FastAPI normalizes middleware interrupts and LangGraph streams into a small SSE protocol.

## Production upgrade path

This repository is intentionally not production-grade. Evolve it in this order:

1. Durable checkpointer (Postgres/Redis-backed option)
2. Authenticated users and persistent thread ownership
3. Real tools / external APIs
4. Approve / edit / reject policies
5. LangSmith tracing and evaluation
6. MCP tools
7. RAG skill
8. Rate limits, security controls, retries, idempotency
9. Deployment and durable side-effect execution

Do not add these before the runtime concepts are understood; otherwise the demo becomes infrastructure-heavy and hides the LangGraph execution model.
