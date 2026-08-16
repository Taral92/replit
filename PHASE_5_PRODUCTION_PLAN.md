# Phase 5 — Production Platform: Persistence, Auth, Durable Runs, Isolation, Billing

> **How to use this file.** This is five gated sub-phases (5A–5E). Execute one at a
> time. Each has acceptance criteria that must pass before the next begins. Do not
> attempt more than one sub-phase per session — 5A alone is a larger diff than all of
> Phase 1.

---

## 0. The security gate — read before anything else

RunnerIDE is being deployed as **hosted SaaS**. That changes the threat model completely.

Today, `services/agent/sandbox/local.py` executes `run_command` as a subprocess on the
host. `services/agent/gateway/policy.py` classifies command risk in Python. **A policy
check is not a security boundary.** Any user who can send a prompt can get code execution
on your server — read other users' workspaces, read your `.env`, exfiltrate your API keys.

> **Hard rule: no public user may touch a hosted instance until Phase 5D
> (container isolation) is complete and verified.**

5A–5C can be built and tested with trusted users only. 5D is the gate on launch. Do not
let a demo, a beta list, or a friend-of-a-friend onto a hosted instance before it lands.

---

## 1. Current state — verified, not assumed

| Concern | Configured | Actually implemented |
|---|---|---|
| Database | `DATABASE_URL` in `settings.py` | **Nothing.** No models, no migrations, no engine. |
| Redis | `REDIS_URL` in `settings.py` | **Nothing.** No client anywhere. |
| S3 | `S3_BUCKET` in `settings.py` | Only `services/runner/src/s3_snapshots.ts`. The Python path never calls it. |
| Auth | — | **None.** No users, no tokens, no middleware. |
| Sessions | — | `session_registry: Dict[str, SessionContext]` — in-memory dict, `main.py:68` |
| Agent memory | — | `MemorySaver()` — in RAM, `runtime.py:72` |
| Isolation | — | `LocalSandbox` — subprocesses on the host |

### The defect that dictates the design

`apps/api/realtime/handlers_agent.py:29`

```python
ctx = get_or_create_session(session_id=sid)   # sid = socket.io connection id
```

A `sid` is regenerated on every reconnect. Consequences:

1. Wifi blip → new `sid` → a brand new `SessionContext`, `LocalSandbox`, `AgentRuntime`
   and `MemorySaver` are constructed. All conversation state is lost.
2. The original agent task keeps running and emits to `room=<old_sid>` — a room with no
   members. The work completes; the output goes nowhere.
3. `uvicorn --reload` restarts on every file save and wipes everything.
4. A second API instance is impossible — there is no shared state.

**Agent lifetime is currently bound to a TCP connection.** Every requirement in this
phase — resumption, history, multi-tenancy, metering — is blocked by that one fact.

---

## 2. Target architecture

```
Client (apps/web)
   │  HTTP: REST for entities        WS: subscribe to run event streams
   ▼
API (apps/api) ── stateless, horizontally scalable
   │
   ├── Postgres   durable entities: users, projects, workspaces, runs, events, usage
   ├── Redis      pub/sub fan-out, presence, locks, rate limits
   ├── S3         workspace snapshots, large tool outputs, artifacts
   │
   └── Worker pool ── runs agent turns as durable jobs, appends to the event log
            │
            └── Sandbox (one container per workspace) ── executes all user code
```

### The core inversion

**An agent run is a durable job, not a socket handler.**

```
POST /v1/runs        → insert run row, enqueue job, return run_id immediately
worker               → executes the agent, appends every event with a sequence number
client               → subscribes to run_id's event stream
reconnect            → GET /v1/runs/{id}/events?after_seq=47, then resume live
```

Once events are an append-only log, reconnection needs no special logic — the client asks
what it missed. That is the entire mechanism. Build it and resumption falls out for free.

---

## 3. Phase 5A — Database foundation

**Goal:** durable storage. Everything else depends on this.

### 5A.1 Stack

- PostgreSQL 15+ (not SQLite — you need concurrent writers and JSONB)
- SQLAlchemy 2.x async + `asyncpg`
- Alembic for migrations

Add a `postgres` service to `docker/` for local development. Update `.env.example`.

### 5A.2 Create `packages/db/`

```
packages/db/
├─ __init__.py
├─ engine.py        async engine + session factory
├─ base.py          declarative Base
├─ models/          one file per aggregate
│  ├─ user.py
│  ├─ project.py
│  ├─ workspace.py
│  ├─ run.py        agent_runs + run_events + tool_calls
│  └─ usage.py      usage_records + budgets
└─ repositories/    query layer — routes never write raw SQL
   ├─ users.py
   ├─ projects.py
   ├─ runs.py
   └─ usage.py
alembic/            migrations
```

**Rule:** routes and handlers call repositories. They never touch the ORM session
directly. This keeps the query surface auditable and testable.

### 5A.3 Schema

All ids are UUID. All timestamps are `timestamptz`. All tenant-scoped tables carry
`user_id` and are indexed on it.

```
users
  id, email (unique), password_hash, name, created_at, last_login_at,
  plan_id, status ('active'|'suspended')

api_keys                       -- BYO provider keys, encrypted at rest
  id, user_id, provider ('openai'|'anthropic'), encrypted_key,
  key_hint (last 4 chars), created_at, revoked_at

projects
  id, user_id, name, slug, created_at, archived_at
  UNIQUE (user_id, slug)

workspaces
  id, project_id, user_id, status ('provisioning'|'running'|'stopped'|'error'),
  container_id, storage_key, last_active_at, created_at
  INDEX (user_id, status)

agent_runs                     -- one row per user turn
  id, workspace_id, user_id, prompt, model, status
    ('queued'|'running'|'completed'|'failed'|'cancelled'),
  started_at, ended_at, duration_ms, error, cancelled_by,
  input_tokens, output_tokens, cost_usd
  INDEX (workspace_id, started_at DESC)

run_events                     -- APPEND ONLY. The resumption mechanism.
  id, run_id, seq (int), type, payload (jsonb), created_at
  UNIQUE (run_id, seq)
  INDEX (run_id, seq)

tool_calls
  id, run_id, seq, tool_name, arguments (jsonb),
  result_ref (S3 key, nullable), result_inline (text, nullable),
  status, risk_level, approved_by, duration_ms, added, removed, diff_ref
  INDEX (run_id)

usage_records                  -- one row per LLM call
  id, user_id, workspace_id, run_id, provider, model,
  input_tokens, output_tokens, cost_usd, created_at
  INDEX (user_id, created_at DESC)

budgets
  user_id (PK), monthly_limit_usd, current_period_start,
  current_period_usd, hard_stop (bool)
```

**Two things to get right:**

1. **`run_events.seq` is monotonic per run.** Allocate it inside the same transaction as
   the insert. This is what makes `?after_seq=N` correct. A gap or duplicate here breaks
   resumption silently.
2. **Never store large tool output in Postgres.** A 4000-char file read per tool call
   across thousands of runs will bloat the table and slow every query. Over ~8KB, write
   to S3 and store the key in `result_ref`. Keep `result_inline` for small results only.

### ✅ 5A acceptance criteria

- `alembic upgrade head` creates every table from a clean database
- `alembic downgrade base` reverses cleanly
- Repository unit tests cover create/read/update for each aggregate
- `docker compose up` starts Postgres and the API together
- **Nothing else changed.** No route, handler, or agent code touches the DB yet.

---

## 4. Phase 5B — Auth and multi-tenancy

**Goal:** real users, and sessions keyed by identity rather than a TCP connection.

### 5B.1 Authentication

- Email + password, hashed with `argon2` or `bcrypt`. Never store plaintext.
- JWT access token (15 min) + refresh token (30 days, rotated, stored hashed in DB).
- `POST /v1/auth/register`, `/login`, `/refresh`, `/logout`, `GET /v1/auth/me`
- FastAPI dependency `get_current_user()` on every protected route.
- Socket.IO: authenticate in the `connect` handler from the auth token. **Reject
  unauthenticated connections.** Do not let an unauthenticated socket reach a handler.

### 5B.2 Re-key sessions — the critical change

Replace:

```python
ctx = get_or_create_session(session_id=sid)          # WRONG
```

with:

```python
ctx = await get_or_create_session(user_id=user.id, workspace_id=workspace_id)
```

`SessionContext` is now keyed by `(user_id, workspace_id)`, not by connection. A reconnect
resolves to the **same** context. This alone fixes conversation loss on disconnect.

Socket.IO rooms become `f"workspace:{workspace_id}"` rather than `sid`, so multiple tabs
and reconnects all receive the same stream.

### 5B.3 Tenant scoping — enforce it in one place

Every workspace-scoped route must verify the workspace belongs to the authenticated user.
Do this in a **single dependency**, not by hand in each route:

```python
async def get_owned_workspace(workspace_id, user = Depends(get_current_user)):
    ws = await workspaces.get(workspace_id)
    if ws is None or ws.user_id != user.id:
        raise HTTPException(404)      # 404, not 403 — do not leak existence
    return ws
```

Audit every existing route in `apps/api/routes/` for missing scoping. `workspace_id` is
currently a path parameter with **no ownership check at all** — today any user could read
any workspace by guessing an id.

### 5B.4 Workspace directories

`settings.get_workspace_dir_for_session()` currently returns a shared default directory.
Change to `{BASE}/{user_id}/{workspace_id}`. Keep `PolicyEngine.resolve_and_validate_path`
enforcing the boundary — it stays the last line of defence.

### ✅ 5B acceptance criteria

- Register, log in, refresh, log out all work end to end
- An unauthenticated socket connection is rejected
- **User A requesting User B's workspace id receives 404** — write a test for this
- Disconnect and reconnect mid-session preserves conversation state
- Two browser tabs on one workspace both receive the same events
- Restarting the API no longer loses user identity

---

## 5. Phase 5C — Durable agent runs

**Goal:** agent turns survive disconnects, restarts, and deploys.

### 5C.1 Decouple the run from the socket

`handlers_agent.py` currently `await`s the entire agent run inside the socket handler.
Replace with:

1. `agent.start` (or `POST /v1/runs`) inserts an `agent_runs` row with status `queued`
   and returns `run_id` **immediately**
2. A background worker picks it up and executes
3. Every event the agent emits is appended to `run_events` with the next `seq`, **then**
   published to Redis for live fan-out
4. Clients subscribe to `workspace:{id}` and receive events as they are published

Order matters: **persist first, then publish.** If you publish first and crash before the
insert, the client has an event that replay will never produce, and the log diverges.

### 5C.2 Replay endpoint

```
GET /v1/runs/{run_id}/events?after_seq=<n>
```

Returns all events with `seq > n`, ordered. On reconnect, the client sends its highest
seen `seq`, receives the gap, then resumes live. Store `lastSeq` in `useAgentStore`.

### 5C.3 Persistent agent memory

Replace `MemorySaver()` in `runtime.py:72` with LangGraph's Postgres checkpointer, scoped
by `thread_id = workspace_id`. This is a much smaller change than reimplementing memory,
and it means agent context survives restarts.

### 5C.4 Orphan recovery

On API startup, find runs with status `running` whose worker is gone. Mark them `failed`
with a clear error, and emit a terminal event so any client replaying the log sees a
completed turn rather than one that streams forever.

### ✅ 5C acceptance criteria

- Start a long run, kill the browser tab, reopen — the run is still progressing and the
  UI catches up via replay
- Start a run, restart the API — the run is marked failed with a clear message, not left
  hanging
- `run_events.seq` has no gaps or duplicates under concurrent load
- Agent conversation context survives an API restart
- `agent.stop` still cancels correctly through the new path

---

## 6. Phase 5D — Container isolation ⚠️ LAUNCH GATE

**Goal:** user code cannot touch the host or other tenants. **Nothing ships publicly
until this passes.**

### 6.1 One container per workspace

`services/agent/sandbox/base.py` already defines the `Sandbox` ABC and `local.py`
implements it. Add `services/agent/sandbox/container.py` implementing the same interface
against Docker (dev) and Kubernetes (prod). `services/workspace_manager/k8s_client.py`
and `lifecycle.py` already exist — wire them.

Required properties per workspace container:

- Non-root user; read-only root filesystem except the workspace volume
- CPU and memory limits; PID limit to stop fork bombs
- No host network. Egress restricted to package registries (npm, PyPI) only —
  **no access to your API, your database, or the metadata endpoint**
- No mounted host paths beyond that workspace's own volume
- Idle timeout: snapshot to S3 and tear down after N minutes of inactivity
- Secrets injected per-container; **never** mount the platform `.env`

### 6.2 Keep the policy layer

`PolicyEngine` stays as defence in depth — but it is now the *second* line, not the only
one. Container isolation is the boundary.

### ✅ 5D acceptance criteria — test these adversarially

- `cat /etc/passwd`, `ls /`, `env` from inside a workspace reveal nothing about the host
- Attempting to reach another workspace's files fails
- `curl` to your own API from inside the sandbox is blocked by network policy
- A fork bomb or memory hog is contained and killed without affecting other workspaces
- Idle containers snapshot and tear down; resuming restores the workspace intact
- Platform API keys are unreachable from inside a container

---

## 7. Phase 5E — Storage, metering, billing hooks

### 7.1 Workspace snapshots (S3)

Port or invoke the logic in `services/runner/src/s3_snapshots.ts`. Snapshot on idle
timeout and on explicit stop; restore on resume. Key: `workspaces/{user_id}/{workspace_id}/`.
Exclude `node_modules`, `.next`, `.venv` — restore by reinstalling, not by copying.

### 7.2 Usage metering

Record one `usage_records` row per LLM call: provider, model, input tokens, output
tokens, computed cost. Aggregate per user per billing period.

Wrap the LLM client so this cannot be forgotten — metering must be impossible to bypass,
not a call site the next feature forgets to add.

### 7.3 Budget enforcement — server-side

Check the budget **before** dispatching a run. Over the limit → reject with a clear error.
Never rely on the client to enforce this.

Two-tier: soft warning at 80%, hard stop at 100% when `hard_stop` is set.

This is the same concern as your iteration cap. The cap bounds one turn; the budget
bounds the month. You need both — a user with an agent in a retry loop is otherwise an
unbounded bill.

### 7.4 BYO API keys

Let users supply their own provider keys, encrypted at rest with a KMS-managed key (not a
hardcoded secret). Usage on a user's own key still gets metered but is not billed.

**This is worth prioritising.** It moves your inference cost to zero for the users who
opt in, which is the difference between a viable early product and one that loses money
on every power user.

### 7.5 Billing hooks

Do not build billing. Emit the events a billing provider consumes: `subscription.created`,
`usage.recorded`, `limit.exceeded`. Integrate Stripe later against those.

### ✅ 5E acceptance criteria

- A workspace snapshots on idle and restores byte-identical on resume
- Every LLM call produces exactly one `usage_records` row
- A user over budget is rejected before the run starts
- A user-supplied key is used, metered, and not billed
- Encrypted keys are unreadable without the KMS key

---

## 8. Execution order and gates

| Phase | Scope | Blocks | Gate |
|---|---|---|---|
| **5A** | Postgres, schema, migrations, repositories | everything | migrations up and down cleanly |
| **5B** | Auth, tenant scoping, re-key sessions | 5C, 5D | cross-tenant access returns 404 |
| **5C** | Durable runs, event log, replay | 5E metering | run survives tab close and API restart |
| **5D** | Container isolation | **public launch** | adversarial tests pass |
| **5E** | Snapshots, metering, budgets, BYO keys | revenue | budget enforced server-side |

One sub-phase per session. Commit at each boundary as `phase(5X): <what changed>`.
Never mix sub-phases in one commit.

**Do not reorder.** 5B without 5A has nowhere to store users. 5C without 5B has no stable
key for a session. 5D last is fine for building, but it is first for launching.
