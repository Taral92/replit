# RunnerIDE — System Architecture (v2)

> AI-powered cloud IDE: pick a stack, get an isolated environment, edit code in-browser,
> run it live, and have an agent that can write files, install packages, and run commands.
> v2 folds in fixes for the volume-path bug, the docker.sock security hole, missing WS auth,
> and single-host scaling — see §9 for a diff against the original draft.

---

## 1. Design Principles

1. **One WebSocket, typed messages** — no REST for anything real-time.
2. **Raw Claude tool-calling loop** — no agent framework. The loop is <100 lines; a
   framework would hide the control flow you need to stream to the browser.
3. **Host filesystem is the container's filesystem** — FileManager and the container
   read/write the *same* path. (v1 had these as two different storage locations — fixed
   here via bind mounts, see §4.3.)
4. **Nothing touches `docker.sock` except one broker process.** The API backend never
   gets host-level control.
5. **Every WebSocket connection is authenticated before `accept()`**, not after.

---

## 2. High-Level Architecture

```
                         ┌─────────────────────────┐
                         │       BROWSER             │
                         │  Monaco │ xterm.js │ Chat │
                         └───────────┬──────────────┘
                                     │ wss://api/ws/{replId}?token=...
                                     │ (JWT validated BEFORE accept)
                ┌────────────────────▼───────────────────┐
                │            FASTAPI BACKEND               │
                │  WS Manager → Message Router              │
                │  terminal_* / file_* / ai_*               │
                └───┬─────────┬─────────┬──────────────┬───┘
                    │         │         │              │
              ┌─────▼──┐ ┌────▼───┐ ┌──▼─────┐   ┌─────▼─────┐
              │Terminal│ │  File  │ │ Agent  │   │ Container │
              │Manager │ │Manager │ │Runner  │   │ Registry  │
              └───┬────┘ └───┬────┘ └───┬────┘   │ (Redis)   │
                  │          │          │        └─────┬─────┘
                  │          │          │              │ repl_id → host
                  └──────────┴────┬─────┘              │
                                   │                    │
                        Internal network only           │
                                   │                    │
                         ┌─────────▼──────────┐         │
                         │   DOCKER BROKER      │◄────────┘
                         │  (only process with  │
                         │   docker.sock access)│
                         │  restricted API:      │
                         │  create / exec / stop │
                         └─────────┬────────────┘
                                   │
              ┌────────────────────▼───────────────────┐
              │              DOCKER HOST                  │
              │  Container (repl A)                       │
              │   bind mount: /data/volumes/{id} ⇄ /workspace │
              │   non-root user, 512MB/0.5CPU limit        │
              │  Container (repl B) ...                    │
              │  Traefik → preview URLs                    │
              └───┬─────────────────────────────────────┘
                  │
           ┌──────▼──────┐        ┌──────────────┐
           │  S3 / R2     │        │  PostgreSQL   │
           │ source of    │        │ users/repls/  │
           │ truth        │        │ messages      │
           └──────────────┘        └──────────────┘
```

**Why a broker process:** the backend that talks to browsers is the thing most exposed
to untrusted input (user prompts, file contents, terminal commands routed through an
agent with `run_command`). If that process also holds `docker.sock`, a bug or prompt
injection there is a host-root escape. The broker is small, does exactly three things
(create container, exec in container, stop container), and is the *only* thing with
socket access. Backend talks to it over an internal-only network — never exposed to
the browser.

---

## 3. Frontend (React) — unchanged from v1

```
src/
├── components/
│   ├── Editor/{MonacoEditor,FileExplorer}.tsx
│   ├── Terminal/Terminal.tsx
│   ├── Chat/{ChatPanel,AgentAction,MessageBubble}.tsx
│   ├── Preview/PreviewFrame.tsx
│   └── Layout/SplitPane.tsx
├── hooks/{useWebSocket,useTerminal,useFileSystem}.ts
└── context/ReplContext.tsx
```

One change: `useWebSocket` must attach the session token when opening the connection —
`new WebSocket(`wss://api/ws/${replId}?token=${authToken}`)` — since the backend now
rejects unauthenticated connections at `accept()` time (§4.2).

---

## 4. Backend (FastAPI)

### 4.1 Structure

```
backend/
├── main.py
├── api/
│   ├── routes/{repl,files}.py
│   └── websocket/{handler,protocol}.py
├── services/
│   ├── docker_broker_client.py   # talks to the broker, never to docker.sock directly
│   ├── file_manager.py
│   ├── terminal_manager.py
│   └── agent_runner.py
├── models/{database,schemas}.py
└── core/{config,s3,redis}.py

broker/                            # separate deployable, own container, own network
├── main.py                        # tiny FastAPI/gRPC service
└── docker_ops.py                  # the only code in the whole system with docker.sock
```

### 4.2 WebSocket Handler — auth-first

```python
# api/websocket/handler.py

async def websocket_endpoint(websocket: WebSocket, repl_id: str, token: str = Query(...)):
    # 1. Validate BEFORE accept() — an unauthenticated socket never opens
    user = await verify_token(token)
    if user is None:
        await websocket.close(code=4401)
        return

    repl = await get_repl(repl_id)
    if repl is None or repl.user_id != user.id:
        await websocket.close(code=4403)  # not your repl
        return

    session = ReplSession(websocket, repl_id, user)
    await session.start()
```

```python
class ReplSession:
    async def start(self):
        await self.ws.accept()

        # Ask the broker to create/reuse the container — backend never calls Docker itself
        container_ref = await self.broker.get_or_create(self.repl_id, self.repl.stack)

        # Record which host this repl is running on (see §6, scaling)
        await self.registry.set(self.repl_id, container_ref.host)

        await self.send("container_ready", {"status": "ok"})

        terminal_task = asyncio.create_task(self.terminal_mgr.stream_output(container_ref, self.ws))
        watcher_task = asyncio.create_task(self.file_mgr.watch_changes(self.repl_id, self.ws))

        try:
            await self.listen_loop(container_ref)
        except WebSocketDisconnect:
            pass
        finally:
            terminal_task.cancel()
            watcher_task.cancel()
            await self.registry.delete(self.repl_id)
```

Message routing (`terminal_input` / `file_save` / `file_read` / `ai_prompt`) is the same
dispatch pattern as v1 — the fix here is entirely in *who's allowed to open the socket
and what it's authorized to touch*, not in the protocol shape.

### 4.3 Docker Broker + fixed volume path

**The v1 bug:** the container mounted a *named Docker volume* (`repl-vol-{id}`) at
`/workspace`, while `FileManager` read/wrote a *host path* (`/data/volumes/{id}`)
directly. Those are two different pieces of storage unless the volume happens to be
configured with that exact host device — which the code never did. The AI agent could
"write" a file that the running container would never actually see.

**Fix: use a bind mount, not a named volume, and make it the single path both sides use.**

```python
# broker/docker_ops.py — the ONLY module in the system touching docker.sock

import docker

class DockerOps:
    def __init__(self):
        self.client = docker.from_env()

    IMAGES = {"react": "runner-react:latest", "nextjs": "runner-nextjs:latest", "python": "runner-python:latest"}

    def create_container(self, repl_id: str, stack: str):
        host_path = f"/data/volumes/{repl_id}"   # same path FileManager uses
        os.makedirs(host_path, exist_ok=True)

        return self.client.containers.run(
            image=self.IMAGES[stack],
            name=f"repl-{repl_id}",
            detach=True, tty=True, stdin_open=True,
            working_dir="/workspace",
            volumes={host_path: {"bind": "/workspace", "mode": "rw"}},  # BIND MOUNT, not named volume
            mem_limit="512m", cpu_period=100000, cpu_quota=50000,
            network_mode="bridge",
            user="1000:1000",   # non-root inside container — see §5
            labels={
                "traefik.enable": "true",
                f"traefik.http.routers.{repl_id}.rule": f"Host(`{repl_id}.preview.localhost`)",
            },
        )
```

Now `FileManager.save_file()` writing to `/data/volumes/{repl_id}/src/App.tsx` on the
host **is** `/workspace/src/App.tsx` inside the container — no divergence, no sync bug.
The broker exposes only `create_container`, `exec_in_container`, `stop_container` to the
backend — not the raw Docker SDK — so a compromised backend still can't run arbitrary
Docker API calls (e.g., mounting `/` into a new container).

### 4.4 File Manager, Terminal Manager, Agent Runner

Unchanged from v1 in logic (pull from S3 on session start → write to the now-correct
bind-mounted path → push to S3 on save; `docker exec -it` for PTY terminal streaming;
Claude tool loop with `read_file` / `write_file` / `run_command` / `list_files`). Two
call-outs:

- **Verify the Claude model string at implementation time** rather than hardcoding one
  from a doc — model identifiers change and a stale one is a silent failure mode.
- **`run_command` executes only inside the sandboxed container**, which is now correctly
  isolated (non-root, resource-limited, no `docker.sock` in reach) — so the agent having
  shell access is contained by §4.3/§5, not by anything in the agent code itself.

---

## 5. Security Model

| Risk | Mitigation |
|---|---|
| Backend process compromise → host root | `docker.sock` isolated in broker; backend has no Docker SDK access at all |
| Cross-user access via guessed repl ID | JWT validated + ownership checked before WS `accept()` |
| Runaway container resource use | `mem_limit=512m`, `cpu_quota=50000` (0.5 core) per container |
| Container → host filesystem escape | Bind mount scoped to one dir per repl; container runs as non-root (`user=1000:1000`) |
| Container → internal network (DB, broker, other users' containers) | `network_mode="bridge"` + firewall rules; containers can't reach backend/Postgres/Redis directly |
| Agent (`run_command`) doing damage | Same container sandbox as above — the agent has no more reach than a manual terminal user |

For a portfolio/demo build, the broker split and non-root user are the two items worth
actually implementing (they're small). gVisor/Firecracker-level isolation is a "if this
goes to production with real users" item, not a v1 requirement.

---

## 6. Scaling: Container Registry

**The v1 gap:** `ContainerManager` used `docker.from_env()` and an in-memory dict —
meaning the mapping of `repl_id → which container / which host` only existed inside one
backend process. Add a second backend replica behind a load balancer and a WS reconnect
can land on a replica that has no idea the container exists.

**Fix:** a shared registry (Redis) that any backend replica can consult.

```
repl_id → { host: "docker-host-3", container_id: "repl-abc123", last_active: ... }
```

- On session start: backend checks Redis — if `repl_id` already has a host, route the
  broker call to *that* host's broker instance; if not, pick a host and record it.
- On disconnect + idle timeout: registry entry cleared, broker stops the container.
- Load balancer / WS gateway needs to either be sticky-by-repl_id, or the registry entry
  needs to include enough info that any backend can proxy the WS to the right broker.

This isn't needed for a single-host demo — it's the thing to add the moment you run more
than one backend instance.

---

## 7. Data Flow (updated)

```
1. Open repl:
   Browser → POST /repl/{id}/open (JWT in header)
     → verify ownership → Redis: any existing host for this repl?
     → Broker.create_or_get(repl_id, stack)  [bind mount, non-root]
     → FileManager.pull_from_s3() → bind-mounted host path
     → returns { status: "ready" }
   Browser → wss://api/ws/{id}?token=...
     → backend validates token + ownership BEFORE accept()
     → ReplSession starts (terminal stream + file watcher)

2. Terminal input/output, file save/read, AI prompt:
   same message-router pattern as v1 (§4.2), all now flowing through
   the broker instead of touching docker.sock directly.

3. AI agent turn:
   ai_prompt → AgentRunner.run() → Claude (tools) → write_file/run_command
     → executes against the broker-managed, bind-mounted, non-root container
     → agent_action + file_update + ai_stream messages back over the same WS
```

---

## 8. Database Schema — unchanged

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE repls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    stack TEXT NOT NULL CHECK (stack IN ('react','nextjs','python')),
    container_id TEXT,
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_active_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repl_id UUID REFERENCES repls(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
    content TEXT NOT NULL,
    tool_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_repls_user ON repls(user_id);
CREATE INDEX idx_messages_repl ON messages(repl_id, created_at);
```

---

## 9. Changelog vs Original Draft

| # | v1 issue | v2 fix |
|---|---|---|
| 1 | Named Docker volume ≠ host path FileManager wrote to — agent's writes could be invisible to the running container | Bind mount at a single shared path (§4.3) |
| 2 | Backend held `docker.sock` directly — any compromise = host root | Dedicated broker process is the only thing with socket access (§2, §4.3) |
| 3 | WS accepted the connection before checking who was on the other end | Token + ownership verified before `accept()` (§4.2) |
| 4 | Hardcoded, likely-stale Claude model string | Verify current model ID at implementation time, don't trust the doc |
| 5 | `docker.from_env()` + in-memory dict — breaks with >1 backend replica | Redis-backed container registry (§6) |

---

## 10. Build Plan

**Phase 1 — Skeleton:** FastAPI + Vite, single WS round-trip works.
**Phase 2 — Container + Terminal:** Broker (§4.3) built here, not bolted on later —
container/terminal manager talk to the broker from day one. `docker exec` PTY → xterm.js.
**Phase 3 — Filesystem:** FileManager against the bind-mounted path; Monaco read/write/save.
**Phase 4 — Auth + Persistence:** JWT + WS auth-before-accept (§4.2); S3 pull/push; Postgres.
**Phase 5 — AI Agent:** Claude tool loop; verify model ID; agent runs inside the now-sandboxed container.
**Phase 6 — Scale-out:** Redis container registry (§6) — only needed once you add a second backend replica.
**Phase 7 — Polish:** Traefik preview URLs, idle cleanup, reconnect handling, UI states.

---

## 11. Tech Stack Summary

| Component | Technology |
|---|---|
| Frontend | React + Vite |
| Editor | Monaco Editor |
| Terminal | xterm.js |
| Backend | FastAPI (Python, asyncio) |
| Docker access | Isolated broker process (only holder of `docker.sock`) |
| Containers | Docker, bind-mounted volumes, non-root |
| Container registry | Redis (repl_id → host mapping) |
| File storage | S3 / Cloudflare R2 (source of truth) |
| Database | PostgreSQL + SQLAlchemy |
| AI Model | Claude (verify current model ID at build time) |
| Agent framework | None — raw tool-calling loop |
| Reverse proxy | Traefik |
| File watching | watchfiles |
| Orchestration (prod) | Kubernetes |
