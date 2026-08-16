# AGENTS.md — Rules for coding agents working in this repo

Any AI agent (Antigravity, Claude Code, Cursor, Codex, Copilot) working here must read
this file first and follow it exactly. It exists to stop agents from breaking a working
system by re-implementing things that already exist.

---

## What this project is

**RunnerIDE** — a browser-based IDE where an AI coding agent reads, writes, and executes
code inside a user's sandboxed workspace. Think Replit + Codex.

Three layers, strictly separated:

| Layer | Location | Responsibility |
|---|---|---|
| **Intelligence** | `services/agent/` | Decides *what* to do. Never touches the filesystem. |
| **Execution** | `services/agent/gateway/` + `services/runner/` | Actually does it. Enforces all policy. |
| **Presentation** | `apps/web/` | Renders server state. Derives no truth of its own. |

If your change requires editing all three, the design is wrong. Stop and reconsider.

---

## Do not read these paths

Reading them wastes context and leads to implementing against dead architecture.

```
*.zip  *.tar.gz
.venv/  node_modules/  __pycache__/  .pytest_cache/
terraform/.terraform/  *.tfstate*
*.tsbuildinfo  package-lock.json
workspaces/            # runtime user data — never source of truth for code
```

---

## Canonical implementations — there is exactly one of each

Historically this repo had 3 agent implementations, 2 runners, 2 workspace managers, and
2 frontends. They were removed. **Do not recreate them.** If you need agent behaviour, it
lives in `services/agent/` — nowhere else.

| Concern | The one true location |
|---|---|
| Agent runtime / reasoning loop | `services/agent/runtime.py` |
| Agent tool definitions | `services/agent/tools.py` |
| Tool execution chokepoint | `services/agent/gateway/tool_gateway.py` |
| Security policy (paths, commands) | `services/agent/gateway/policy.py` |
| Sandbox (pty, processes, ports) | `services/agent/sandbox/local.py` |
| HTTP + WebSocket gateway | `apps/api/` |
| Long-running process runner | `services/runner/` (TypeScript) |
| Workspace lifecycle / k8s | `services/workspace_manager/` |
| Frontend | `apps/web/` (Vite + React + TypeScript + Tailwind) |
| Shared config | `packages/config/settings.py` |
| Event contract | `packages/protocol/events.py` (+ generated `types.ts`) |

**Deleted, never to return:** `python_agent/`, `orchestrator/`, `runner/`, `workspace/`,
`services/workspace-manager/` (hyphen), `frontend/`.

---

## Hard invariants

### 1. All tool execution goes through the gateway

No file write, shell command, or process spawn may bypass
`services/agent/gateway/tool_gateway.py`. If you find yourself importing `subprocess`,
`os.remove`, or `open(..., "w")` outside `sandbox/` — stop. That is the bug.

### 2. Paths are validated before use, always

Every user- or agent-supplied path goes through
`PolicyEngine.resolve_and_validate_path(base_dir, requested_path)`. It returns
`(ok, resolved, error)`. Never `Path(base) / user_input` directly — that is a path
traversal vulnerability.

### 3. Workspace roots are per-session

`settings.get_workspace_dir_for_session(session_id, workspace_id)` is the only way to
resolve a workspace directory. Never hardcode a workspace path, and never let one session
read another's files.

### 4. The event contract is generated, not hand-written

`packages/protocol/events.py` is authoritative. `packages/protocol/types.ts` is generated
from it. If you add an event you must:

1. Add the Pydantic model in `events.py`
2. Regenerate `types.ts`
3. Emit it from `apps/api/realtime/`
4. Handle it in `apps/web/src/hooks/useSocketBridge.ts`

All four, in one commit. Never invent an ad-hoc socket string.

### 5. All HTTP calls live in one file

`apps/web/src/lib/api.ts`. No `fetch()` anywhere else in the frontend. Base URL comes
from `import.meta.env.VITE_API_URL` — never a hardcoded host.

### 6. All state lives in zustand stores

`apps/web/src/store/`. Components read from stores and render. They do not hold server
state in `useState`, and they do not subscribe to sockets directly —
`useSocketBridge.ts` is the single place where socket events become store updates.

### 7. Design tokens only

Every colour, spacing value, radius, and duration comes from CSS custom properties in
`apps/web/src/styles/theme.css`, consumed through Tailwind semantic classes.

**Banned in `apps/web/src/components/`:** hex literals, `rgb()`/`rgba()` literals, inline
`style={{}}` objects (the sole exception is a genuinely dynamic value such as a computed
pixel width), arbitrary Tailwind values like `text-[13px]`.

### 8. API routes are versioned

`/v1/workspaces/{workspace_id}/...`. Do not add unversioned routes. Do not add a second
route that does the same thing as an existing one.

---

## UI conventions

Follow these or the interface will drift out of visual consistency:

- UI text 12–13px; list/tree rows exactly 24px; panel padding 8–12px.
- Icons 14–16px, `strokeWidth={1.5}`.
- Panel dividers are `1px solid var(--border-subtle)` — a barely visible hairline.
- Hover changes background only, never border width (it causes a 1px reflow).
- Focus rings are inset: `box-shadow: inset 0 0 0 1px var(--accent)`.
- One accent hue. Blue means interactive or active — nothing else.
- Transitions ≤ 200ms, `var(--ease-out)`. Nothing animates on mount except streaming text.
- Text truncates with ellipsis; the full value goes in a tooltip. Never wrap in rows/tabs.
- Interactive primitives come from `components/ui/` (Radix-backed). Do not hand-roll a
  dropdown, dialog, tooltip, or context menu.

---

## Before you commit

```bash
cd apps/web && npm run build          # must pass
cd ../.. && make test                 # must pass

! grep -rE "#[0-9a-fA-F]{6}" apps/web/src/components/
! grep -r  "style={{"          apps/web/src/components/
! grep -r  "localhost:8000"    apps/web/src/
```

Commit messages: `<type>(<scope>): <what>` — e.g. `feat(agent-panel): collapse tool rows`.

---

## When you are unsure

Ask rather than guess. Specifically, do not decide on your own to:

- add a new top-level directory
- add a dependency (especially a UI or state library — the stack is fixed: React, Vite,
  TypeScript, Tailwind, zustand, Radix, framer-motion, cmdk, Monaco, xterm)
- change the event protocol
- alter anything in `gateway/policy.py` (that is the security boundary)
- reformat or restructure a file you were not asked to change
