# demo-stream-01

Minimal end-to-end demo of **LangChain + LangGraph Router + Skills + Streaming + Human-in-the-Loop (HITL) + React UI**.

The project intentionally avoids RAG, databases, MCP, authentication, queues, and cloud infrastructure so the runtime behavior stays visible.

## What this demo teaches

```text
User
  |
  v
Router
  |----------------------|
  |                      |
  v                      v
general              summarize
  |                      |
  |                 load SKILL.md
  |                      |
  v                      v
LLM streaming         LLM streaming
  |                      |
  v                      v
 END                    END

Router
  |
  v
support_reply
  |
  v
load SKILL.md
  |
  v
stream draft
  |
  v
interrupt()
  |
  +---- Reject ---> END
  |
  +---- Approve --> fake_send --> data/outbox.jsonl --> END
```

## Stack

- Backend: Python 3.11+, FastAPI, LangGraph 1.2.x, LangChain OpenAI
- Frontend: React 18, TypeScript, Vite
- Graph streaming: LangGraph Event Streaming v3 (`messages`, `custom`, interrupts)
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
│   │   │   └── state.py
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
router -> support_reply -> approval [PAUSE]
                                 |
                              approve
                                 |
                                 v
                                send -> END
```

The generated draft streams before the graph pauses. Click **Approve**. The fake send action appends one JSON line to:

```text
backend/data/outbox.jsonl
```

### Support reply + reject

Use the same prompt, then click **Reject**.

Expected:

```text
router -> support_reply -> approval [PAUSE] -> END
```

No outbox record is written.

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

to execute the model-backed routes, verify skill events, pause/resume HITL, and assert the streamed tool progress sequence `0 → 30 → 60 → 90 → 100`.

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

The backend uses LangGraph Event Streaming v3 as the runtime-facing API and adapts its typed projections to this intentionally small SSE contract. The frontend does not know LangGraph internals; it only renders these application events.

> LangGraph 1.2.x currently marks Event Streaming v3 as experimental. This demo uses it because it is the current recommended direction for new applications, while keeping the browser protocol small enough to swap the backend streaming adapter later if the API changes.

## Core learning points

1. **Router is not an agent.** It returns a structured route decision.
2. **Skills are progressively loaded.** Only the chosen `SKILL.md` enters the model context.
3. **Use native message streaming for model output.** Nodes call `model.ainvoke()`; `run.messages` exposes text deltas without custom token plumbing.
4. **Use custom events for domain progress.** Skills, routing and tool progress still use `get_stream_writer()` because they are application-specific events.
5. **HITL really pauses execution.** The graph requires a checkpointer and the same `thread_id` to resume.
6. **Direct `interrupt()` is intentional here.** `HumanInTheLoopMiddleware` is designed for `create_agent` tool calls; this demo has a deterministic `support_reply -> approval -> send` workflow, so the lower-level primitive is simpler and more precise.
7. **Side effects happen after approval.** Nothing irreversible is executed before the interrupt.
8. **Frontend stays dumb.** It renders stream events; workflow policy remains server-side.

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
