# RunnerIDE — Codex-Grade Rebuild: Implementation Prompt

> **How to use this file.** Paste this entire document into Antigravity (Gemini Pro) as the
> task brief. Execute **phases in order**. Do not skip ahead. After each phase, stop and
> confirm the acceptance criteria pass before starting the next one.

---

## 0. Read this first — operating rules for the agent

You are working on **RunnerIDE**, an online IDE (a Replit/Codex hybrid) where an AI coding
agent can read, write, and execute code inside a user's sandboxed workspace.

**Rules that must never be violated:**

1. **Only read files listed in §1.2 (Canonical file map).** The repository contains large
   dead directories and a 185 MB `project.zip`. Reading them wastes your context and will
   make you implement against the wrong architecture. If a file is not in the canonical map
   and not created by you, do not open it.
2. **Never open, index, or reason about:** `project.zip`, `repl_backup.tar.gz`, `.venv/`,
   `orchestrator/venv/`, `node_modules/`, `__pycache__/`, `.pytest_cache/`,
   `terraform/.terraform/`, `*.tsbuildinfo`, `package-lock.json`.
3. **One change set per phase.** Do not refactor code belonging to a later phase.
4. **Never break the wire contract** defined in §4 without updating both sides in the
   same commit.
5. When a phase says *delete*, delete — do not comment out, do not rename to `.old`.
6. Every new UI component must consume design tokens from `src/styles/theme.css`.
   Zero hardcoded hex values in component files. This is a hard gate.

---

## 1. Current state — audit findings

### 1.1 What is actually broken

This is not a greenfield project. The repo has real, working code buried under three
generations of abandoned attempts. Here is the honest state:

| # | Problem | Evidence | Impact |
|---|---------|----------|--------|
| **P0** | **The agent's sandbox writes into a dead frontend.** `settings.BASE_WORKSPACE_DIR` defaults to `<repo>/workspace`, but `workspace/` is also an abandoned Next.js 16 app (`package.json`, `next.config.mjs`, `src/app/`). | `packages/config/settings.py:23-26` vs `workspace/package.json` | User project files and a stale framework scaffold are interleaved. Agents `list_dir` and see Next.js config that has nothing to do with the user's project. **This is why the agent gets confused.** |
| **P0** | **Three competing agent implementations.** | `python_agent/` (agents/architect, engineer, monitor, supervisor + langgraph `orchestrator/graph.py`), `services/agent/` (runtime + tool gateway + verifier), `orchestrator/main.py` (FastAPI k8s orchestrator) | Only `services/agent/` is wired into `apps/api/main.py`. The other two are dead weight the agent keeps re-reading. |
| **P0** | **Two competing event vocabularies.** `packages/protocol/events.py` defines `agent.start` / `agent.message` / `agent.tool.started`. The live socket.io layer emits `ai:turn_start` / `ai:message` / `ai:tool_call` / `ai:step` / `ai:activity`. | `apps/api/main.py:377-549` vs `packages/protocol/events.py` | The typed protocol package is decorative. Frontend listens to the untyped strings. Any agent editing one side silently breaks the other. |
| **P1** | **Two runners.** `runner/` (JS, `server.js` is a 10-line stub, mixed with React `App.js`/`App.css`) and `services/runner/` (TypeScript, real `process_manager.ts` + `s3_snapshots.ts`). | Both present, `Makefile` only references `services/runner` | Dead code. |
| **P1** | **Two workspace managers.** `services/workspace_manager/` (underscore) and `services/workspace-manager/` (hyphen). | Both directories exist | Import ambiguity on case/format. |
| **P1** | **Two frontends.** `frontend/` (Vite + React, 12 real components, ~2800 LOC, actively developed) and `workspace/` (Next.js, `page.tsx` is 69 lines of scaffold). | — | Ambiguous entry point. |
| **P1** | **Dual API surface.** Every file route is registered twice: legacy `/files` and versioned `/v1/workspaces/{workspace_id}/files`. The frontend only calls the legacy ones with hardcoded `http://localhost:8000`. | `apps/api/main.py:136-190`, `frontend/src/components/Sidebar.tsx:71` | Multi-tenancy is stubbed but unreachable. |
| **P2** | **All styling is inline `style={{}}` objects.** ~2800 lines of components with per-element inline styles referencing a JS `tokens` object. No Tailwind, no CSS variables, no hover/focus states, no transitions beyond ad-hoc ones. | `frontend/src/App.tsx`, all components | Cannot achieve Codex-level polish. Impossible to theme. Impossible to keep consistent. |
| **P1** | **Six live contract breaks between frontend and backend** — routes called that don't exist, events listened for that are never emitted. See §1.3. | verified by grep | Features that look implemented are silently 404-ing. |
| **P2** | 185 MB `project.zip` + 480 KB `repl_backup.tar.gz` committed at repo root. | — | Bloats every clone and every agent index. |

### 1.3 Verified contract drift — fix all of these in Phase 1

These were confirmed by grepping both sides. They are real, current bugs:

| # | Break | Detail |
|---|---|---|
| 1 | `POST /files/create` → **404** | Called by `Sidebar.tsx:161`. No such route in `main.py`. New-file creation is broken. |
| 2 | `POST /folders/create` → **404** | Called by `Sidebar.tsx:155`. No such route. New-folder creation is broken. |
| 3 | `server:crashed` | `Preview.tsx` listens for it. The backend never emits it. Crash UI is dead code. |
| 4 | `terminal:resize` | `Terminal.tsx` emits it. No `@sio.on("terminal:resize")` handler exists — the pty never resizes, so output wraps wrongly. |
| 5 | `ai:status`, `ports:update` | Emitted by the backend, listened for by nobody. Status and port info are thrown away. |
| 6 | `template:init` | `@sio.on("template:init")` exists at `main.py:360`. No frontend caller. Dead handler. |
| 7 | No health endpoint | There is no `/health` route at all. Create `GET /v1/health` — the Makefile, Docker healthchecks, and k8s probes all need one. |

When you unify the protocol (§3.4), resolve each of these: implement the missing route or
handler, or delete the dead listener. Do not leave a listener without an emitter.

### 1.2 Canonical file map — the ONLY files that matter

**Backend (keep, all of these are live):**

```
apps/api/main.py                        581 LOC  — FastAPI + socket.io gateway. THE entry point.
apps/api/models.py                               — request/response models
packages/config/settings.py              74 LOC  — pydantic Settings (BASE_WORKSPACE_DIR bug lives here)
packages/config/__init__.py
packages/protocol/events.py             183 LOC  — typed events (currently unused by the socket layer)
packages/protocol/types.ts              191 LOC  — TS mirror of the above
services/agent/runtime.py               399 LOC  — AgentRuntime.run_stream(), langgraph graph builder
services/agent/tools.py                 166 LOC  — 14 agent tools (see §3.3)
services/agent/context.py               100 LOC  — context window management
services/agent/router.py                 98 LOC  — model routing
services/agent/verifier.py              404 LOC  — post-edit verification loop
services/agent/gateway/tool_gateway.py           — the single chokepoint for all tool execution
services/agent/gateway/policy.py                 — path validation, command risk classification
services/agent/sandbox/base.py                   — Sandbox ABC
services/agent/sandbox/local.py                  — LocalSandbox (pty, port detection, process mgmt)
services/agent/sandbox/models.py
services/runner/src/index.ts            227 LOC  — Node runner HTTP/WS server
services/runner/src/process_manager.ts  134 LOC  — long-running process supervision
services/runner/src/s3_snapshots.ts      95 LOC  — workspace snapshot/restore
```

**Frontend (keep the logic, rebuild the presentation):**

```
frontend/src/App.tsx                    242 LOC  — layout shell, socket lifecycle, panel state
frontend/src/components/AiPanel.tsx     790 LOC  — agent chat, sessions, streaming  ← biggest rewrite
frontend/src/components/Preview.tsx     538 LOC  — iframe live preview, port switching
frontend/src/components/Sidebar.tsx     479 LOC  — file tree, CRUD, undo toast
frontend/src/components/TurnSummary.tsx 413 LOC  — agent turn / diff rendering
frontend/src/components/Editor.tsx      329 LOC  — Monaco + tab bar
frontend/src/components/ActivityBar.tsx 256 LOC
frontend/src/components/AgentActivity.tsx 191 LOC
frontend/src/components/Terminal.tsx    108 LOC  — xterm
frontend/src/components/StatusBar.tsx   107 LOC
frontend/src/components/PanelEmptyState.tsx 108 LOC
frontend/src/components/ResizeHandle.tsx 64 LOC
frontend/src/hooks/useWebSocket.ts
frontend/src/hooks/useAgentTurns.ts
frontend/src/styles/tokens.ts                    — JS token object, to be replaced by CSS vars
frontend/src/styles/global.css
```

**Infra (keep, do not touch in this task):** `docker/`, `k8s/`, `terraform/`,
`.github/workflows/`, `tests/`, `Makefile`.

**Everything else is dead.** See Phase 1.

---

## 2. Target architecture

### 2.1 Target directory tree

```
runner-ide/
├─ AGENTS.md                     # agent guardrails — read by every coding agent
├─ README.md
├─ Makefile
├─ .gitignore
├─ .env.example
│
├─ apps/
│  ├─ web/                       # ← renamed from frontend/. Vite + React 18 + TS + Tailwind
│  │  ├─ index.html
│  │  ├─ vite.config.ts
│  │  ├─ tailwind.config.ts
│  │  ├─ package.json
│  │  └─ src/
│  │     ├─ main.tsx
│  │     ├─ App.tsx              # ONLY layout composition. No business logic.
│  │     ├─ styles/
│  │     │  ├─ theme.css         # CSS custom properties — the single source of design truth
│  │     │  └─ global.css
│  │     ├─ lib/
│  │     │  ├─ api.ts            # every HTTP call. No fetch() outside this file.
│  │     │  ├─ socket.ts         # socket.io singleton + typed event map
│  │     │  ├─ events.ts         # TS types mirroring packages/protocol
│  │     │  └─ utils.ts          # cn(), formatBytes, langFromPath, etc.
│  │     ├─ store/               # zustand stores — all app state lives here
│  │     │  ├─ useWorkspaceStore.ts   # file tree, open tabs, active file, dirty set
│  │     │  ├─ useAgentStore.ts       # turns, steps, streaming buffer, sessions
│  │     │  ├─ useRuntimeStore.ts     # server status, ports, terminal buffer
│  │     │  └─ useUiStore.ts          # panel visibility, sizes, theme, command palette
│  │     ├─ hooks/
│  │     │  ├─ useSocketBridge.ts     # ONE place that maps socket events → stores
│  │     │  ├─ useKeybindings.ts
│  │     │  └─ useFileTree.ts
│  │     ├─ components/
│  │     │  ├─ ui/               # primitives: Button, IconButton, Tooltip, Dropdown,
│  │     │  │                    # Dialog, Tabs, ScrollArea, Badge, Spinner, Skeleton,
│  │     │  │                    # Kbd, ContextMenu, Toast, Resizable
│  │     │  ├─ layout/           # AppShell, TitleBar, ActivityBar, StatusBar, PanelGroup
│  │     │  ├─ explorer/         # FileTree, FileTreeNode, FileIcon, ExplorerToolbar,
│  │     │  │                    # NewItemInput, DeleteConfirm
│  │     │  ├─ editor/           # EditorPane, TabBar, Tab, MonacoHost, Breadcrumbs,
│  │     │  │                    # DiffViewer, EmptyEditor
│  │     │  ├─ agent/            # ← the Codex-defining surface. See §5.
│  │     │  │  ├─ AgentPanel.tsx
│  │     │  │  ├─ Composer.tsx
│  │     │  │  ├─ TurnList.tsx
│  │     │  │  ├─ TurnItem.tsx
│  │     │  │  ├─ MessageBlock.tsx
│  │     │  │  ├─ ToolCallRow.tsx
│  │     │  │  ├─ DiffCard.tsx
│  │     │  │  ├─ PlanChecklist.tsx
│  │     │  │  ├─ ApprovalPrompt.tsx
│  │     │  │  ├─ ThinkingIndicator.tsx
│  │     │  │  └─ SessionSwitcher.tsx
│  │     │  ├─ terminal/         # TerminalPane, TerminalTabs
│  │     │  ├─ preview/          # PreviewPane, PreviewToolbar, PortSelector, DeviceFrame
│  │     │  └─ palette/          # CommandPalette, FileQuickOpen
│  │     └─ types/
│  │        └─ index.ts
│  │
│  └─ api/                       # unchanged location
│     ├─ main.py                 # slimmed: routing + socket wiring only
│     ├─ models.py
│     ├─ routes/                 # NEW — extracted from main.py
│     │  ├─ files.py
│     │  ├─ workspace.py
│     │  └─ health.py
│     └─ realtime/               # NEW — extracted from main.py
│        ├─ socket_server.py
│        ├─ handlers_agent.py
│        ├─ handlers_terminal.py
│        └─ handlers_server.py
│
├─ services/
│  ├─ agent/                     # unchanged — this is the good implementation
│  ├─ runner/                    # TypeScript runner (the survivor)
│  └─ workspace_manager/         # single underscore version only
│
├─ packages/
│  ├─ config/
│  └─ protocol/                  # events.py + types.ts — now ACTUALLY enforced
│
├─ workspaces/                   # ← NEW. Runtime sandbox root. gitignored.
│  └─ .gitkeep                   #    BASE_WORKSPACE_DIR points here.
│
├─ docker/  k8s/  terraform/  tests/  .github/
```

### 2.2 The architectural rule that prevents agents from breaking things

> **Intelligence is separate from execution, and both are separate from presentation.**

- `services/agent/` decides *what* to do. It never touches the filesystem directly.
- `services/agent/gateway/tool_gateway.py` is **the single chokepoint**. Every file write,
  every shell command, every process spawn goes through it. Policy is enforced here and
  nowhere else.
- `apps/api/` translates between the outside world and the gateway. It holds no logic.
- `apps/web/` renders state. It never derives truth; it mirrors what the server says.

If a change requires touching all three layers, the design is wrong. Reconsider.

---

## 3. Phase 1 — Structural cleanup

**Goal:** one implementation per concern. Do this first; every later phase depends on it.

### 3.1 Delete

```bash
git rm -r --cached project.zip repl_backup.tar.gz
rm -f project.zip repl_backup.tar.gz
rm -rf python_agent/          # superseded by services/agent/
rm -rf orchestrator/          # superseded by services/workspace_manager/
rm -rf runner/                # superseded by services/runner/
rm -rf services/workspace-manager/   # hyphen duplicate; keep the underscore one
rm -rf .pytest_cache/ terraform/.terraform/
rm -f terraform.tfstate terraform/terraform.tfstate terraform/terraform.tfstate.backup
rm -f workspace/tsconfig.tsbuildinfo
```

Before deleting `services/workspace-manager/`, diff it against
`services/workspace_manager/` and port anything unique (`k8s_client.py`, `lifecycle.py`
appear only in the hyphen version — move them across, then delete).

### 3.2 Fix the workspace-root collision (P0)

1. Create `workspaces/` at repo root with a `.gitkeep`.
2. In `packages/config/settings.py`, change the default:

```python
BASE_WORKSPACE_DIR: Path = Field(
    default_factory=lambda: Path(
        os.environ.get("WORKSPACE_DIR", _project_root / "workspaces")
    )
)
```

3. Delete the legacy Next.js app: `rm -rf workspace/`.
4. Add to `.gitignore`:

```
workspaces/*
!workspaces/.gitkeep
*.zip
*.tar.gz
.venv/
__pycache__/
.pytest_cache/
node_modules/
*.tsbuildinfo
.terraform/
*.tfstate*
.env
```

### 3.3 Rename and relocate the frontend

```bash
git mv frontend apps/web
```

Update `Makefile`, `docker/Dockerfile.*`, `.github/workflows/*` to the new path.

### 3.4 Unify the event protocol (P0)

`packages/protocol/events.py` is authoritative. The socket layer must emit event names
derived from it. Perform a mechanical rename across `apps/api/` and `apps/web/`:

| Old (socket.io string) | New (canonical) |
|---|---|
| `ai:turn_start`   | `agent.turn.started` |
| `ai:message`      | `agent.message` |
| `ai:turn_end`     | `agent.turn.completed` |
| `ai:step`         | `agent.step` |
| `ai:tool_call`    | `agent.tool.started` / `agent.tool.completed` |
| `ai:activity`     | *(delete — it duplicated `ai:step`)* |
| `ai:status`       | `agent.status` |
| `ai:chat`         | `agent.start` |
| `terminal:data`   | `terminal.output` |
| `terminal:write`  | `terminal.input` |
| `files:changed`   | `files.changed` |
| `server:ready`    | `preview.ready` |
| `server:status`   | `server.status` |
| `ports:update`    | `ports.update` |
| `server:start` / `server:stop` | `server.start` / `server.stop` |
| `terminal:resize` | `terminal.resize` — **and add the missing handler** |
| `server:crashed`  | `server.crashed` — **and add the missing emitter** |
| `template:init`   | *(delete — no caller)* |

Regenerate `packages/protocol/types.ts` from `events.py` so the TS types and Pydantic
models cannot drift. Add a test that fails if an event name exists on one side only.

### 3.5 Collapse the dual API surface

Delete the legacy unversioned routes (`/files`, `/files/content`, `/files/save`,
`/files/delete`, `/workspace/wipe`). Keep only:

```
GET    /v1/workspaces/{workspace_id}/files
GET    /v1/workspaces/{workspace_id}/files/content?path=
PUT    /v1/workspaces/{workspace_id}/files/content
POST   /v1/workspaces/{workspace_id}/files          (create file/folder — NEW, see §1.3)
DELETE /v1/workspaces/{workspace_id}/files?path=
POST   /v1/workspaces/{workspace_id}/reset
GET    /v1/health                                   (NEW — does not exist today)
```

Note that `POST .../files` and `GET /v1/health` are **new routes you must write**, not
renames. The frontend already calls the former under two different legacy paths that were
never implemented.

Frontend calls go through `apps/web/src/lib/api.ts` only. Base URL from
`import.meta.env.VITE_API_URL` — **remove every hardcoded `http://localhost:8000`**
(currently in `Sidebar.tsx`, `Editor.tsx`, `App.tsx`, `Preview.tsx`).

### 3.6 Split `apps/api/main.py`

581 lines in one file is why agents keep breaking it. Extract into `routes/` and
`realtime/` per §2.1. `main.py` should end up under 80 lines: app construction, CORS,
lifespan, router includes, socket mount.

### ✅ Phase 1 acceptance criteria

- `find . -name "*.py" -path "*agent*" -not -path "*/.venv/*"` returns files under
  `services/agent/` only.
- `git ls-files | xargs du -ch | tail -1` is under 5 MB.
- `make run-api` boots and `GET /v1/health` returns 200.
- `grep -r "localhost:8000" apps/web/src/` returns nothing.
- `grep -rE "ai:(chat|message|step|status)" apps/ services/` returns nothing.
- The file tree in the UI shows an empty workspace, not a Next.js scaffold.
- Creating a file and creating a folder from the explorer both succeed (no 404).
- Resizing the terminal reflows the pty output correctly.
- Every `socket.on(...)` in `apps/web/` has a matching emitter in `apps/api/`, and vice
  versa. Add a test that asserts this by parsing both sides.

---

## 4. Phase 2 — The design system

**Goal:** make Codex-grade polish mechanically achievable. No UI work happens before this.

### 4.1 Install

```bash
cd apps/web
npm i -D tailwindcss postcss autoprefixer tailwind-merge
npm i clsx zustand @radix-ui/react-tooltip @radix-ui/react-dropdown-menu \
      @radix-ui/react-dialog @radix-ui/react-context-menu @radix-ui/react-scroll-area \
      cmdk framer-motion
npx tailwindcss init -p
```

Radix gives you accessible, unstyled primitives — correct focus trapping, keyboard nav,
and portal behaviour out of the box. That is exactly the layer where hand-rolled UIs feel
cheap.

### 4.2 `src/styles/theme.css` — the single source of design truth

```css
:root {
  /* ── Surfaces: 5 elevation steps, low contrast between adjacent steps.
        Codex reads "calm" because adjacent surfaces differ by ~3% luminance,
        never by a hard border alone. ── */
  --surface-0:  #0a0a0b;   /* app background */
  --surface-1:  #101012;   /* panels: sidebar, agent panel */
  --surface-2:  #161619;   /* raised: tab bar, toolbars, inputs */
  --surface-3:  #1c1c20;   /* hover states */
  --surface-4:  #232328;   /* active / selected */

  /* ── Borders: hairlines, never pure grey ── */
  --border-subtle: #1e1e22;   /* default dividers — barely visible, that's correct */
  --border-default:#2a2a30;
  --border-strong: #3a3a42;   /* focus rings, active panel edge */

  /* ── Text: 4 steps, generous contrast on primary ── */
  --text-primary:  #ededf0;
  --text-secondary:#a1a1ab;
  --text-tertiary: #6e6e78;
  --text-disabled: #4a4a52;

  /* ── Accent: single hue. Resist adding a second. ── */
  --accent:        #4b8cf5;
  --accent-hover:  #649bf7;
  --accent-muted:  rgba(75, 140, 245, 0.14);
  --accent-border: rgba(75, 140, 245, 0.35);

  /* ── Semantic ── */
  --success: #2ea043;  --success-muted: rgba(46,160,67,0.14);
  --warning: #d29922;  --warning-muted: rgba(210,153,34,0.14);
  --danger:  #e5534b;  --danger-muted:  rgba(229,83,75,0.14);

  /* ── Diff ── */
  --diff-add-bg:    rgba(46,160,67,0.13);
  --diff-add-text:  #56d364;
  --diff-del-bg:    rgba(229,83,75,0.13);
  --diff-del-text:  #f85149;
  --diff-gutter:    #17171a;

  /* ── Type: system stack for UI, one mono for code ── */
  --font-ui:   ui-sans-serif, -apple-system, "Inter", "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;

  --text-2xs: 10px;  --text-xs: 11px;  --text-sm: 12px;
  --text-base: 13px; --text-md: 14px;  --text-lg: 16px;

  /* ── Space: 4px base grid. Every margin/padding is a multiple. ── */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 20px; --space-6: 24px; --space-8: 32px;

  --radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px; --radius-xl: 12px;

  /* ── Elevation: soft, never harsh ── */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.35);
  --shadow-lg: 0 12px 32px rgba(0,0,0,0.45);

  /* ── Motion: fast is professional. Nothing over 200ms. ── */
  --ease-out:  cubic-bezier(0.16, 1, 0.3, 1);
  --dur-fast:  120ms;
  --dur-base:  180ms;

  /* ── Fixed chrome dimensions ── */
  --h-titlebar: 36px;
  --h-tabbar:   34px;
  --h-statusbar:24px;
  --w-activitybar: 44px;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

Wire these into `tailwind.config.ts` as named tokens (`bg-surface-1`, `text-secondary`,
`border-subtle`) so components use semantic class names, never raw values.

### 4.3 Build `components/ui/` primitives

Build these **before** any feature component. Every one must support: `disabled`,
`:focus-visible` ring using `--accent`, and a `className` passthrough merged via
`cn()` (clsx + tailwind-merge).

`Button` (variants: primary / secondary / ghost / danger; sizes: sm / md) ·
`IconButton` (square, tooltip-required) · `Tooltip` (Radix, 400ms delay, 11px) ·
`DropdownMenu` · `Dialog` · `ContextMenu` · `Tabs` · `ScrollArea` (custom 8px thin
scrollbars, `--border-strong` thumb) · `Badge` · `Spinner` · `Skeleton` (shimmer) ·
`Kbd` · `Toast` · `Separator` · `Resizable` (wrap `react-resizable-panels`; 1px handle
that becomes 3px `--accent` on hover after 100ms delay).

### 4.4 The rules that actually produce "Codex feel"

These are the details that separate a polished IDE from a competent one. Follow all of them.

1. **Hairline borders, not boxes.** Panels are separated by `1px solid var(--border-subtle)`
   — a border you can barely see. Never use `--border-strong` for layout dividers.
2. **Density.** UI text is 12–13px. Row height in file tree and tool call lists is exactly
   24px. Padding inside panels is 8–12px, never 16px+.
3. **No pure black, no pure white.** `#0a0a0b` and `#ededf0` are the extremes.
4. **One accent colour.** Blue means "interactive or active." Nothing else is blue.
5. **Hover is a background change, never a border change.** Border changes cause a 1px
   reflow shimmer that reads as amateur.
6. **Focus rings are inset**: `box-shadow: inset 0 0 0 1px var(--accent)`. Outer rings
   clip inside scroll containers.
7. **Every icon is 14px or 16px, `strokeWidth={1.5}`.** Lucide's default 2 is too heavy
   at IDE density.
8. **Text truncates with `text-overflow: ellipsis`, never wraps** in tree rows, tabs, or
   status bars. Full value goes in a tooltip.
9. **Empty states always offer an action**, never just say "nothing here."
10. **Loading is skeletons, not spinners** — except for indeterminate agent work, which
    gets a pulsing dot.
11. **Nothing animates on mount** except agent messages (they fade in over 180ms as they
    stream). Layout must feel instant.
12. **Scrollbars are always thin and only visible on hover** over the scroll container.

---

## 5. Phase 3 — The agent panel (the defining surface)

This is what makes it read as "Codex" rather than "a chat box bolted to an IDE." The
current `AiPanel.tsx` is 790 lines of inline styles doing everything — split it into the
components listed in §2.1 and rebuild the visual language as follows.

### 5.1 Turn anatomy

A **turn** = one user prompt and everything the agent did in response. Render it as a
vertical stack with a 2px left rail in `--border-subtle`, indented 12px:

```
┌─────────────────────────────────────────────────┐
│  ▎ You                              14:32       │  ← 11px --text-tertiary, uppercase-ish
│  ▎ add dark mode toggle to settings             │  ← 13px --text-primary
│                                                  │
│  ▎ ◐ Thinking                            2.4s   │  ← collapses to a summary when done
│  ▎                                               │
│  ▎ ▸ Read  src/components/Settings.tsx    ·  ✓  │  ← 24px rows, mono path, 14px icon
│  ▎ ▸ Grep  "theme"                    3 hits ✓  │
│  ▎ ▾ Edit  src/components/Settings.tsx  +12 -3  │  ← expanded → DiffCard below
│  ▎   ┌───────────────────────────────────────┐  │
│  ▎   │ 24  const [theme, setTheme] = ...     │  │
│  ▎   │ 25 +  const toggle = () => ...        │  │  ← --diff-add-bg, no full-row highlight
│  ▎   │ 26 -  return <div>                    │  │
│  ▎   └───────────────────────────────────────┘  │
│  ▎                                               │
│  ▎ Added a theme toggle wired to the existing    │  ← assistant prose, 13px, 1.6 leading
│  ▎ ThemeContext. The switch persists to…        │
│  ▎                                               │
│  ▎ 3 files changed  ·  8.2s  ·  ⧉ Review diff   │  ← turn footer, 11px --text-tertiary
└─────────────────────────────────────────────────┘
```

**Non-negotiables:**

- **Tool calls collapse by default.** One 24px row each: chevron, 14px icon, verb, mono
  argument (truncated), right-aligned result chip. Click expands. This is the single most
  important thing — an agent panel that dumps raw tool output is unreadable.
- **The completed-turn default is collapsed detail, expanded prose.** Users read the
  summary; they expand tools only when something looks wrong.
- **Streaming text fades in per-chunk** (opacity 0→1, 180ms). No typewriter effect, no
  layout jump. Reserve height so the scroll position doesn't jitter.
- **Auto-scroll follows the stream, but stops the instant the user scrolls up.** Show a
  "↓ Jump to latest" pill when detached. Getting this wrong makes the panel unusable.
- **Errors render as a `--danger-muted` card** with the failing command in mono and a
  "Retry" button — never as red prose.

### 5.2 Plan checklist

When the agent emits a plan, render a persistent checklist pinned above the composer:

```
Plan                                    2/4
✓ Locate the settings component
✓ Read the existing theme context
◐ Add the toggle control
○ Verify the build passes
```

Completed items are `--text-tertiary` with a strikethrough-free check; the in-progress
item is `--text-primary` with a pulsing dot. This is the highest-value trust signal in the
whole product — the user always knows where the agent is.

### 5.3 Approval prompts

Your `policy.py` already has `requires_human_approval(risk)`. Surface it: when a
high-risk command is classified, render an inline card in the turn stream with the command
in mono, a plain-language risk description, and **Approve** / **Reject** buttons. Block the
composer while pending. Do not use a modal — modals break the reading flow.

### 5.4 Composer

Auto-growing textarea, 3 rows min / 12 max, `--surface-2`, 1px `--border-default`,
focus → `--accent-border`. Below it, a single 28px row: model selector (ghost dropdown),
`@` file-mention button, and a send button that becomes a stop button while streaming.
`Cmd/Ctrl+Enter` sends; `Enter` newlines when the input is multi-line. `@` opens inline
file search over the workspace tree.

---

## 6. Phase 4 — The rest of the IDE

### 6.1 Layout shell

```
┌────────────────────────────────────────────────────────────────┐
│ ⬡ RunnerIDE   project-name         ● Live      ⌘K   ⚙  ▣ ▤ ▥ │ 36px titlebar
├──┬──────────────┬─────────────────────────┬────────────────────┤
│▣ │ EXPLORER  ⟳+ │ App.tsx ×  utils.ts ×   │ AGENT       ⟳ ⋯   │
│▤ │              ├─────────────────────────┤                    │
│⌕ │ ▾ src        │                         │  (agent panel)     │
│⎇ │   ▾ components│      Monaco            │                    │
│⚙ │     App.tsx  │                         │                    │
│  │              ├─────────────────────────┤                    │
│  │              │ TERMINAL  PROBLEMS  ⌄   │                    │
│  │              │ $ npm run dev           │                    │
├──┴──────────────┴─────────────────────────┴────────────────────┤
│ main ✓   0 ⚠ 0 ⓧ   TypeScript   Ln 24, Col 8   :3000 ●        │ 24px statusbar
└────────────────────────────────────────────────────────────────┘
```

Persist all panel sizes and visibility to `localStorage` via `useUiStore`. Restoring the
exact layout on reload is a small thing that makes the product feel owned.

### 6.2 File explorer

24px rows · 12px indent per depth · chevron only on folders (14px, rotates 90° over
120ms) · file-type icons via `lucide-react`, colour-coded by extension · single click
opens a **preview tab** (italic title, replaced by the next single click) · double click
pins it · right-click context menu (New File, New Folder, Rename, Duplicate, Copy Path,
Delete) · inline rename, not a dialog · drag to move · **files the agent modified in the
current turn get a 4px `--accent` left bar for 3 seconds** — a small touch that makes agent
work legible.

### 6.3 Editor

Monaco with a custom theme built from `theme.css` — do not use `vs-dark`; matching the
surrounding chrome exactly is what makes it feel integrated. Tabs are 34px, max 200px
wide, dirty state is a 6px dot replacing the close ✕ until hover. Breadcrumbs below the
tab bar, 11px, `--text-tertiary`. Add: `Cmd+S` save, `Cmd+P` quick open, `Cmd+Shift+F`
project search, format-on-save, and a diff mode that opens when a `DiffCard` is clicked.

### 6.4 Terminal

xterm with `FitAddon` + `WebLinksAddon`, `--font-mono` at 12px, cursor blink,
theme derived from `theme.css`. Multiple tabs backed by the existing pty session
registry. A "Clear" and a "Kill" button in the tab strip.

### 6.5 Preview

Keep the existing port-detection logic in `Preview.tsx` — it works. Rebuild the chrome:
a 32px toolbar with back/forward/reload, an editable URL field, a port selector populated
from `ports.update`, device-width presets (Desktop / Tablet / Mobile), and an "open in new
tab" button. When no server is running, show an empty state with a **Start dev server**
button that emits `server.start`.

### 6.6 Command palette

`cmdk`, `Cmd+K`. Fuzzy over: commands, open files, all workspace files, and agent
sessions. This single feature does more for perceived professionalism than any amount of
visual polish.

---

## 7. Phase 5 — Verification

Run these and fix everything they surface. Do not report the task complete until all pass.

```bash
# Structure
test ! -d python_agent && test ! -d orchestrator && test ! -d runner && test ! -d workspace
test -d apps/web && test -d workspaces
git ls-files | xargs du -ch | tail -1        # < 5 MB

# No hardcoded design values in components
! grep -rE "#[0-9a-fA-F]{6}" apps/web/src/components/
! grep -r "style={{" apps/web/src/components/

# No hardcoded URLs, no orphan events
! grep -r "localhost:8000" apps/web/src/
! grep -rE "\bai:(chat|message|step|status|turn_start|turn_end|tool_call|activity)\b" apps/ services/

# Builds and tests
cd apps/web && npm run build
cd ../.. && make test
```

**Manual checks — an agent must actually exercise these, not assume them:**

1. Ask the agent to create a React component. Confirm: plan checklist appears, tool rows
   collapse, diff renders, the file appears in the tree with the accent bar, and the
   editor opens it.
2. Scroll up mid-stream. Confirm auto-scroll detaches and the "Jump to latest" pill shows.
3. Trigger a high-risk command (`rm -rf`). Confirm the approval card blocks the composer.
4. Resize every panel, reload. Confirm the layout is restored exactly.
5. Tab through the whole UI with the keyboard. Every interactive element must show a
   visible focus ring.
6. `prefers-reduced-motion: reduce` — confirm animation is suppressed.

---

## 8. Execution order — do not deviate

| Phase | Scope | Gate before proceeding |
|---|---|---|
| 1 | Delete dead code, fix workspace root, unify protocol, split `main.py` | API boots, health 200, file tree clean |
| 2 | Tailwind + `theme.css` + `components/ui/` primitives | Every primitive renders in isolation with focus states |
| 3 | Agent panel rebuild | Full agent turn renders correctly end to end |
| 4 | Explorer, editor, terminal, preview, palette | All panels functional, layout persists |
| 5 | Verification sweep | Every check in §7 passes |

Commit at each phase boundary with a message of the form
`phase(N): <what changed>`. Never mix phases in one commit.
