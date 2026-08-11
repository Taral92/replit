# 🧠 RunnerIDE — AI-Powered Cloud IDE

> **What**: A platform where users select a tech stack (React, Next.js, Python), get an isolated cloud environment, edit code in-browser, run it live, and have an AI agent that can autonomously write code, install packages, and fix errors.
>
> **Inspired by**: [hkirat/repl](https://github.com/hkirat/repl) + [YouTube walkthrough](https://youtu.be/s0kBqGpThp0)

---

## Table of Contents

1. [The Problem We're Solving](#1-the-problem-were-solving)
2. [Architecture Overview](#2-architecture-overview)
3. [How I Would Build This — My Approach](#3-how-i-would-build-this--my-approach)
4. [Layer 1: Frontend (React)](#4-layer-1-frontend-react)
5. [Layer 2: Backend (FastAPI)](#5-layer-2-backend-fastapi)
6. [Layer 3: Container Runtime (Docker)](#6-layer-3-container-runtime-docker)
7. [Layer 4: File Persistence (S3/R2)](#7-layer-4-file-persistence-s3r2)
8. [Layer 5: AI Agent (Claude)](#8-layer-5-ai-agent-claude)
9. [Layer 6: Live Preview Routing](#9-layer-6-live-preview-routing)
10. [Data Flow — Every User Action](#10-data-flow--every-user-action)
11. [Database Design](#11-database-design)
12. [Project Structure](#12-project-structure)
13. [Build Plan](#13-build-plan)
14. [Hard Problems & How I'd Solve Them](#14-hard-problems--how-id-solve-them)
15. [Tech Stack Summary](#15-tech-stack-summary)

---

## 1. The Problem We're Solving

A user wants to:
1. Pick a stack (React, Next.js, Python Flask)
2. Instantly get a running environment — no local setup
3. Edit files in a Monaco editor (VS Code-like)
4. See a live terminal — run `npm install`, `python app.py`, etc.
5. Chat with an AI that can **actually edit their files and run commands**
6. Come back later and find everything where they left it

The challenge is doing all of this **securely**, **in real-time**, and with **persistent storage**.

---

## 2. Architecture Overview

### High-Level Diagram

```
                         ┌─────────────────────────┐
                         │       BROWSER            │
                         │  ┌──────┐ ┌──────────┐  │
                         │  │Monaco│ │ xterm.js  │  │
                         │  │Editor│ │ Terminal  │  │
                         │  └──┬───┘ └────┬─────┘  │
                         │     │    ┌─────┘         │
                         │  ┌──▼────▼──┐            │
                         │  │ AI Chat  │            │
                         │  │ Panel    │            │
                         │  └────┬─────┘            │
                         └───────┼──────────────────┘
                                 │
                    Single WebSocket connection
                         ws://api/ws/{replId}
                                 │
                ┌────────────────▼────────────────────┐
                │         FASTAPI SERVER               │
                │                                      │
                │  ┌──────────┐  ┌──────────────────┐  │
                │  │ WebSocket│  │  REST API         │  │
                │  │ Manager  │  │  /repl/create     │  │
                │  │          │  │  /repl/{id}/files  │  │
                │  └────┬─────┘  └──────────────────┘  │
                │       │                              │
                │  ┌────▼─────────────────────────┐    │
                │  │  Message Router               │    │
                │  │  terminal_* → ContainerMgr    │    │
                │  │  file_*     → FileMgr         │    │
                │  │  ai_*       → AgentRunner     │    │
                │  └──┬──────────┬──────────┬──────┘    │
                │     │          │          │          │
                │  ┌──▼──┐  ┌───▼───┐  ┌───▼──────┐  │
                │  │Container│ │ File  │  │  Agent  │  │
                │  │Manager  │ │Manager│  │  Runner │  │
                │  └──┬──────┘ └───┬───┘  └───┬─────┘  │
                │     │            │          │        │
                │  ┌──▼────────────▼──────────▼─────┐  │
                │  │         PostgreSQL              │  │
                │  │  users | repls | messages       │  │
                │  └────────────────────────────────┘  │
                └───┬──────────────┬──────────────────┘
                    │              │
          ┌─────────▼───┐   ┌─────▼──────────────────┐
          │  S3 / R2    │   │  Docker Host            │
          │             │   │  ┌───────────────────┐  │
          │  /users/    │   │  │ Container (user A) │  │
          │    /{uid}/  │◄──│  │ /workspace/        │  │
          │      /files │   │  │ node-pty shell     │  │
          │             │   │  │ watchfiles agent   │  │
          │             │   │  └───────────────────┘  │
          │             │   │  ┌───────────────────┐  │
          │             │   │  │ Container (user B) │  │
          │             │◄──│  │ /workspace/        │  │
          │             │   │  └───────────────────┘  │
          └─────────────┘   │                        │
                            │  ┌───────────────────┐  │
                            │  │ Traefik Proxy      │  │
                            │  │ routes preview URLs │  │
                            │  └───────────────────┘  │
                            └────────────────────────┘
```

### The Core Insight

Everything flows through **one WebSocket connection per repl session**. The backend is a **message router** — it receives typed messages and dispatches them to the right handler. This is simpler and faster than separate REST endpoints for every action.

---

## 3. How I Would Build This — My Approach

### Philosophy

I would **not** use any heavy framework for the agent (no LangChain, no CrewAI). I would **not** use Socket.io. I would keep the architecture as flat as possible:

```
Browser ── 1 WebSocket ── FastAPI ── Docker Container
                              └──── Claude API (tools)
                              └──── S3 (files)
                              └──── PostgreSQL (metadata)
```

**Three principles:**

1. **One WebSocket, typed messages** — no REST for real-time stuff
2. **Raw Claude API with tool calling** — I control the loop, not a framework
3. **Hybrid storage** — local Docker volume for speed, S3 for durability

### Why These Choices?

**FastAPI over Express:**
- Python's `asyncio` is excellent for concurrent I/O (websockets + docker + S3)
- Same language as all AI/ML tooling — no context-switching
- Native WebSocket support, no third-party library needed
- Pydantic for strict message validation

**Raw Claude API over LangChain:**
- We need to stream every tool call to the browser in real-time
- LangChain's abstractions hide the control flow — we need full visibility
- The tool loop is simple (< 100 lines) — a framework adds complexity without benefit
- Easier to debug when things go wrong

**Docker over e2b (for learning):**
- You learn how containers actually work
- Full control over the runtime environment
- No per-sandbox cost
- Easy to move to Kubernetes later

---

## 4. Layer 1: Frontend (React)

### Layout

```
┌──────────────────────────────────────────────────┐
│  [Logo]   RunnerIDE   [Stack: React ▼]   [user]  │ ← Header
├────────────┬──────────────────────┬──────────────┤
│            │                      │              │
│  File      │   Monaco Editor      │  AI Chat     │
│  Explorer  │                      │  Panel       │
│            │                      │              │
│  📁 src    │   // App.tsx         │  🤖 Ask AI   │
│   📄App   │   export default     │              │
│   📄index │   function App() {   │  User: build │
│  📁public  │     return <div>    │  a login page│
│            │   }                  │              │
│            │                      │  Agent:      │
│            │                      │  ✅ wrote    │
│            │                      │    Login.tsx  │
│            │                      │  ✅ ran npm  │
│            │                      │    install   │
│            │                      │              │
├────────────┴──────────────────────┴──────────────┤
│  $ npm run dev                                    │ ← xterm.js
│  > Local: http://localhost:3000                   │   Terminal
│  > ready in 500ms                                 │
└──────────────────────────────────────────────────┘
```

### Key React Components

```
src/
├── components/
│   ├── Editor/
│   │   ├── MonacoEditor.tsx       # Monaco wrapper with WebSocket sync
│   │   └── FileExplorer.tsx       # Tree view of /workspace files
│   ├── Terminal/
│   │   └── Terminal.tsx           # xterm.js wrapper
│   ├── Chat/
│   │   ├── ChatPanel.tsx          # AI conversation UI
│   │   ├── AgentAction.tsx        # Shows "✅ wrote file X" actions
│   │   └── MessageBubble.tsx      # User / AI message
│   ├── Preview/
│   │   └── PreviewFrame.tsx       # iframe showing user's running app
│   └── Layout/
│       └── SplitPane.tsx          # Resizable panel layout
├── hooks/
│   ├── useWebSocket.ts            # Single WS connection manager
│   ├── useTerminal.ts             # Terminal state
│   └── useFileSystem.ts           # File tree state
├── context/
│   └── ReplContext.tsx            # Repl ID, container status, etc.
└── App.tsx
```

### The WebSocket Hook (Most Important Piece)

```typescript
// hooks/useWebSocket.ts — single connection, multiplexed messages

function useWebSocket(replId: string) {
  const ws = useRef<WebSocket | null>(null);
  const handlers = useRef<Map<string, Function>>(new Map());

  useEffect(() => {
    ws.current = new WebSocket(`ws://localhost:8000/ws/${replId}`);
    
    ws.current.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      // Route to registered handler based on message type
      const handler = handlers.current.get(msg.type);
      if (handler) handler(msg.payload);
    };

    return () => ws.current?.close();
  }, [replId]);

  const send = (type: string, payload: any) => {
    ws.current?.send(JSON.stringify({ type, payload }));
  };

  const on = (type: string, handler: Function) => {
    handlers.current.set(type, handler);
  };

  return { send, on };
}
```

Each component registers for the message types it cares about:
- Terminal component listens for `terminal_output`
- Monaco listens for `file_update`
- Chat panel listens for `ai_stream` and `agent_action`

---

## 5. Layer 2: Backend (FastAPI)

### Project Structure

```
backend/
├── main.py                        # FastAPI app, CORS, startup/shutdown
├── api/
│   ├── routes/
│   │   ├── repl.py                # REST: create repl, list repls
│   │   └── files.py               # REST: file tree, download
│   └── websocket/
│       ├── handler.py             # Main WS endpoint + message router
│       └── protocol.py           # Pydantic models for all message types
├── services/
│   ├── container_manager.py       # Docker container lifecycle
│   ├── file_manager.py            # S3 read/write + local sync
│   ├── terminal_manager.py        # PTY / docker exec streaming
│   └── agent_runner.py            # AI tool-calling loop
├── models/
│   ├── database.py                # SQLAlchemy models
│   └── schemas.py                 # Pydantic request/response schemas
├── core/
│   ├── config.py                  # Settings (env vars)
│   └── s3.py                     # S3/R2 client setup
├── docker_images/
│   ├── react/Dockerfile           # React stack image
│   ├── nextjs/Dockerfile          # Next.js stack image
│   └── python/Dockerfile          # Python stack image
└── requirements.txt
```

### The WebSocket Handler — Heart of the System

```python
# api/websocket/handler.py

from fastapi import WebSocket, WebSocketDisconnect
from services.container_manager import ContainerManager
from services.terminal_manager import TerminalManager
from services.agent_runner import AgentRunner
from services.file_manager import FileManager

class ReplSession:
    """One instance per active WebSocket connection"""
    
    def __init__(self, websocket: WebSocket, repl_id: str):
        self.ws = websocket
        self.repl_id = repl_id
        self.container_mgr = ContainerManager()
        self.terminal_mgr = TerminalManager()
        self.file_mgr = FileManager()
        self.agent = AgentRunner()
    
    async def start(self):
        """Main entry point — runs for the lifetime of the connection"""
        await self.ws.accept()
        
        # 1. Spin up container (or reuse existing)
        container = await self.container_mgr.get_or_create(
            self.repl_id
        )
        await self.send("container_ready", {"status": "ok"})
        
        # 2. Start the terminal output stream (background task)
        terminal_task = asyncio.create_task(
            self.terminal_mgr.stream_output(container, self.ws)
        )
        
        # 3. Start the file watcher stream (background task)
        watcher_task = asyncio.create_task(
            self.file_mgr.watch_changes(self.repl_id, self.ws)
        )
        
        # 4. Listen for browser messages (main loop)
        try:
            await self.listen_loop(container)
        except WebSocketDisconnect:
            pass
        finally:
            terminal_task.cancel()
            watcher_task.cancel()
    
    async def listen_loop(self, container):
        """Routes incoming messages to the right handler"""
        while True:
            raw = await self.ws.receive_json()
            msg_type = raw["type"]
            payload = raw["payload"]
            
            if msg_type == "terminal_input":
                await self.terminal_mgr.write_input(
                    container, payload["data"]
                )
            
            elif msg_type == "file_save":
                await self.file_mgr.save_file(
                    self.repl_id, 
                    payload["path"], 
                    payload["content"]
                )
            
            elif msg_type == "file_read":
                content = await self.file_mgr.read_file(
                    self.repl_id, payload["path"]
                )
                await self.send("file_content", {
                    "path": payload["path"], 
                    "content": content
                })
            
            elif msg_type == "ai_prompt":
                # Run agent in background — streams results via WS
                asyncio.create_task(
                    self.agent.run(
                        prompt=payload["message"],
                        repl_id=self.repl_id,
                        container=container,
                        websocket=self.ws
                    )
                )
    
    async def send(self, msg_type: str, payload: dict):
        await self.ws.send_json({"type": msg_type, "payload": payload})
```

### Message Protocol (Pydantic Validated)

```python
# api/websocket/protocol.py

from pydantic import BaseModel, Literal
from typing import Union

class TerminalInput(BaseModel):
    type: Literal["terminal_input"]
    payload: dict  # { "data": "npm install\r" }

class FileSave(BaseModel):
    type: Literal["file_save"]
    payload: dict  # { "path": "/src/App.tsx", "content": "..." }

class AIPrompt(BaseModel):
    type: Literal["ai_prompt"]
    payload: dict  # { "message": "build a login page" }

# Server → Browser
class TerminalOutput(BaseModel):
    type: Literal["terminal_output"]
    payload: dict  # { "data": "added 50 packages..." }

class FileUpdate(BaseModel):
    type: Literal["file_update"]
    payload: dict  # { "path": "/src/Login.tsx", "action": "created" }

class AIStream(BaseModel):
    type: Literal["ai_stream"]
    payload: dict  # { "chunk": "I'll create a Login component..." }

class AgentAction(BaseModel):
    type: Literal["agent_action"]
    payload: dict  # { "tool": "write_file", "path": "...", "status": "done" }
```

---

## 6. Layer 3: Container Runtime (Docker)

### How Containers Work

```
Each repl gets exactly ONE Docker container.

Container = Linux box with:
  - Node.js / Python pre-installed
  - /workspace/ directory (volume-mounted)
  - A running shell (bash) that we talk to via docker exec
  - Resource limits (512MB RAM, 0.5 CPU core)
```

### Container Manager Implementation

```python
# services/container_manager.py

import docker
import asyncio
from datetime import datetime, timedelta

class ContainerManager:
    def __init__(self):
        self.client = docker.from_env()
        self._containers: dict[str, docker.models.containers.Container] = {}
        self._last_active: dict[str, datetime] = {}
    
    # Stack → Docker image mapping
    IMAGES = {
        "react":  "runner-react:latest",
        "nextjs": "runner-nextjs:latest",
        "python": "runner-python:latest",
    }
    
    async def get_or_create(self, repl_id: str, stack: str = "react"):
        # Return existing container if alive
        if repl_id in self._containers:
            container = self._containers[repl_id]
            container.reload()
            if container.status == "running":
                self._last_active[repl_id] = datetime.utcnow()
                return container
        
        # Create new container
        container = await asyncio.to_thread(
            self.client.containers.run,
            image=self.IMAGES[stack],
            name=f"repl-{repl_id}",
            detach=True,
            stdin_open=True,
            tty=True,
            working_dir="/workspace",
            volumes={
                f"repl-vol-{repl_id}": {
                    "bind": "/workspace",
                    "mode": "rw"
                }
            },
            # Security + resource limits
            mem_limit="512m",
            cpu_period=100000,
            cpu_quota=50000,  # 50% of 1 CPU
            network_mode="bridge",
            # Labels for Traefik routing
            labels={
                "traefik.enable": "true",
                f"traefik.http.routers.{repl_id}.rule":
                    f"Host(`{repl_id}.preview.localhost`)",
            }
        )
        
        self._containers[repl_id] = container
        self._last_active[repl_id] = datetime.utcnow()
        return container
    
    async def cleanup_idle(self, max_idle_minutes: int = 10):
        """Run periodically to kill idle containers"""
        now = datetime.utcnow()
        to_remove = []
        
        for repl_id, last in self._last_active.items():
            if now - last > timedelta(minutes=max_idle_minutes):
                to_remove.append(repl_id)
        
        for repl_id in to_remove:
            container = self._containers.pop(repl_id)
            await asyncio.to_thread(container.stop, timeout=5)
            await asyncio.to_thread(container.remove)
            del self._last_active[repl_id]
```

### Docker Images Per Stack

```dockerfile
# docker_images/react/Dockerfile

FROM node:20-slim

WORKDIR /workspace

# Pre-install common tools
RUN npm install -g vite create-vite typescript

# Install watchfiles for file change detection
RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install watchfiles boto3

# Default template — overwritten by S3 sync on start
COPY template/ /workspace/

# Keep container alive
CMD ["tail", "-f", "/dev/null"]
```

```dockerfile
# docker_images/python/Dockerfile

FROM python:3.12-slim

WORKDIR /workspace

RUN pip install fastapi uvicorn flask requests watchfiles boto3

COPY template/ /workspace/

CMD ["tail", "-f", "/dev/null"]
```

---

## 7. Layer 4: File Persistence (S3/R2)

### The Strategy

```
                    SOURCE OF TRUTH
                    ┌───────────┐
                    │   S3 / R2  │
                    │  /repls/   │
                    │   /{id}/   │
                    │    /src/   │
                    │    /pkg/   │
                    └─────┬─────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
     On Session Start  On File Save   On Session End
     (pull all files)  (push changed) (force sync all)
          │               │               │
          ▼               ▼               ▼
    ┌───────────────────────────────────────┐
    │  Docker Volume  /workspace/           │
    │  (fast local filesystem)              │
    │  This is what the container reads     │
    │  and writes to during the session     │
    └───────────────────────────────────────┘
```

### File Manager Implementation

```python
# services/file_manager.py

import boto3
import os
import asyncio
from watchfiles import awatch, Change

class FileManager:
    def __init__(self):
        self.s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT"),     # R2 or S3
            aws_access_key_id=os.getenv("S3_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET"),
        )
        self.bucket = os.getenv("S3_BUCKET", "runner-files")
    
    async def pull_from_s3(self, repl_id: str, local_path: str = "/workspace"):
        """Download all files from S3 to local volume on session start"""
        prefix = f"repls/{repl_id}/"
        response = await asyncio.to_thread(
            self.s3.list_objects_v2, Bucket=self.bucket, Prefix=prefix
        )
        
        for obj in response.get("Contents", []):
            key = obj["Key"]
            relative = key.replace(prefix, "")
            dest = os.path.join(local_path, relative)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            await asyncio.to_thread(
                self.s3.download_file, self.bucket, key, dest
            )
    
    async def push_to_s3(self, repl_id: str, file_path: str, content: bytes):
        """Upload a single file to S3"""
        key = f"repls/{repl_id}/{file_path.lstrip('/')}"
        await asyncio.to_thread(
            self.s3.put_object,
            Bucket=self.bucket, Key=key, Body=content
        )
    
    async def save_file(self, repl_id: str, path: str, content: str):
        """Write file locally AND push to S3"""
        local_path = f"/data/volumes/{repl_id}{path}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        with open(local_path, "w") as f:
            f.write(content)
        
        # Background push to S3 (don't block the user)
        asyncio.create_task(
            self.push_to_s3(repl_id, path, content.encode())
        )
    
    async def read_file(self, repl_id: str, path: str) -> str:
        """Read from local volume (fast)"""
        local_path = f"/data/volumes/{repl_id}{path}"
        with open(local_path, "r") as f:
            return f.read()
    
    async def list_files(self, repl_id: str, directory: str = "/") -> list:
        """List file tree from local volume"""
        base = f"/data/volumes/{repl_id}{directory}"
        tree = []
        for root, dirs, files in os.walk(base):
            # Skip node_modules, __pycache__, .git
            dirs[:] = [d for d in dirs if d not in 
                       {"node_modules", "__pycache__", ".git", ".next"}]
            for f in files:
                full = os.path.join(root, f)
                relative = full.replace(f"/data/volumes/{repl_id}", "")
                tree.append(relative)
        return tree
    
    async def watch_changes(self, repl_id: str, websocket):
        """Watch for file changes and notify the browser"""
        watch_path = f"/data/volumes/{repl_id}"
        async for changes in awatch(watch_path):
            for change_type, path in changes:
                relative = path.replace(watch_path, "")
                # Skip node_modules etc.
                if any(skip in relative for skip in 
                       ["/node_modules/", "/__pycache__/", "/.git/"]):
                    continue
                
                await websocket.send_json({
                    "type": "file_update",
                    "payload": {
                        "path": relative,
                        "action": "modified" if change_type == Change.modified 
                                  else "created" if change_type == Change.added
                                  else "deleted"
                    }
                })
```

---

## 8. Layer 5: AI Agent (Claude)

This is the most interesting part. I would build the agent as a **simple while loop with tool calling** — no framework.

### The Agent Runner

```python
# services/agent_runner.py

import anthropic
import json
from services.file_manager import FileManager
from services.container_manager import ContainerManager

class AgentRunner:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic()
        self.file_mgr = FileManager()
    
    # Tools the AI can use
    TOOLS = [
        {
            "name": "read_file",
            "description": "Read the contents of a file in the workspace",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root, e.g. /src/App.tsx"
                    }
                },
                "required": ["path"]
            }
        },
        {
            "name": "write_file",
            "description": "Create or overwrite a file. Provide the COMPLETE file content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path, e.g. /src/pages/Login.tsx"
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete file content"
                    }
                },
                "required": ["path", "content"]
            }
        },
        {
            "name": "run_command",
            "description": "Execute a shell command in the container (e.g. npm install, python script.py). Returns stdout + stderr.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run"
                    }
                },
                "required": ["command"]
            }
        },
        {
            "name": "list_files",
            "description": "List all files in a directory (excludes node_modules, __pycache__)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path, e.g. /src"
                    }
                },
                "required": ["directory"]
            }
        }
    ]
    
    SYSTEM_PROMPT = """You are an expert software engineer working inside a cloud IDE.
You have access to a real filesystem and terminal in the user's project container.

When the user asks you to build something:
1. First, list_files to understand the current project structure
2. Read relevant files to understand existing code
3. Write new files or modify existing ones
4. Run commands to install dependencies or test the code
5. If a command fails, read the error and fix it

Always write COMPLETE file contents — never use placeholders or '...'.
After making changes, run the build/dev command to verify everything works."""
    
    async def run(self, prompt: str, repl_id: str, container, websocket):
        """The main agent loop — reason, act, observe, repeat"""
        
        # Build context: inject current file tree
        file_tree = await self.file_mgr.list_files(repl_id)
        context = f"Current project files:\n{json.dumps(file_tree, indent=2)}"
        
        messages = [
            {"role": "user", "content": f"{context}\n\nUser request: {prompt}"}
        ]
        
        max_iterations = 20  # safety limit
        
        for i in range(max_iterations):
            # Call Claude
            response = await self.client.messages.create(
                model="claude-sonnet-4-5-20250514",
                max_tokens=8096,
                system=self.SYSTEM_PROMPT,
                tools=self.TOOLS,
                messages=messages
            )
            
            # Stream text content to browser
            for block in response.content:
                if block.type == "text" and block.text:
                    await websocket.send_json({
                        "type": "ai_stream",
                        "payload": {"chunk": block.text}
                    })
            
            # If no tool calls, agent is done
            if response.stop_reason != "tool_use":
                await websocket.send_json({
                    "type": "ai_done",
                    "payload": {"message": "Task complete"}
                })
                break
            
            # Execute each tool call
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                
                result = await self._execute_tool(
                    block.name, block.input, repl_id, container
                )
                
                # Tell browser what the agent just did
                await websocket.send_json({
                    "type": "agent_action",
                    "payload": {
                        "tool": block.name,
                        "input": block.input,
                        "result": result[:500],  # truncate for UI
                        "status": "success"
                    }
                })
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })
            
            # Feed results back to Claude → it continues thinking
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
    
    async def _execute_tool(self, name, input_data, repl_id, container):
        """Actually execute a tool against the container/filesystem"""
        
        if name == "read_file":
            return await self.file_mgr.read_file(repl_id, input_data["path"])
        
        elif name == "write_file":
            await self.file_mgr.save_file(
                repl_id, input_data["path"], input_data["content"]
            )
            return f"File written: {input_data['path']}"
        
        elif name == "run_command":
            import asyncio
            exit_code, output = await asyncio.to_thread(
                container.exec_run,
                ["bash", "-c", input_data["command"]],
                workdir="/workspace"
            )
            return output.decode("utf-8", errors="replace")
        
        elif name == "list_files":
            files = await self.file_mgr.list_files(
                repl_id, input_data["directory"]
            )
            return json.dumps(files)
        
        return "Unknown tool"
```

### Why This Works Well

```
User: "Add authentication with JWT"
      ↓
Agent: list_files("/")  → sees package.json, src/App.tsx
Agent: read_file("/package.json")  → sees current deps
Agent: run_command("npm install jsonwebtoken bcryptjs")  → installs
Agent: write_file("/src/auth/jwt.ts", "...")  → creates auth module
Agent: write_file("/src/pages/Login.tsx", "...")  → creates login page
Agent: read_file("/src/App.tsx")  → reads current router
Agent: write_file("/src/App.tsx", "...updated with routes...")
Agent: run_command("npm run build")  → checks for errors
  → Build error: missing import
Agent: read_file("/src/auth/jwt.ts")  → reads its own code
Agent: write_file("/src/auth/jwt.ts", "...fixed...")  → fixes import
Agent: run_command("npm run build")  → success ✅
Agent: "Done! I've added JWT authentication..."
```

Every single step is streamed to the browser as `agent_action` messages. The user sees the agent working in real-time.

---

## 9. Layer 6: Live Preview Routing

When the user's app runs on port 3000 inside the container, they need a URL to access it.

### Traefik Setup

```yaml
# docker-compose.yml (includes Traefik)

version: "3.8"

services:
  traefik:
    image: traefik:v3.0
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--entrypoints.web.address=:80"
    ports:
      - "80:80"
      - "8080:8080"  # Traefik dashboard
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
  
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # access Docker API
      - repl-data:/data/volumes
    environment:
      - S3_ENDPOINT=...
      - S3_KEY=...
      - S3_SECRET=...
      - ANTHROPIC_API_KEY=...
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: runner
      POSTGRES_USER: runner
      POSTGRES_PASSWORD: secret
    volumes:
      - pg-data:/var/lib/postgresql/data

volumes:
  repl-data:
  pg-data:
```

When a container is created with the right Traefik labels, it automatically gets a routable URL:

```
Container repl-abc123 running user's app on port 3000
      ↓
Traefik sees label: Host(`abc123.preview.localhost`)
      ↓
User visits: http://abc123.preview.localhost → sees their running app
```

---

## 10. Data Flow — Every User Action

### Flow 1: User Opens a Repl

```
Browser: POST /repl/{id}/open
  → FastAPI: check DB for repl metadata (stack, user)
  → ContainerManager: create Docker container with stack image
  → FileManager: pull files from S3 into Docker volume
  → FastAPI: returns { status: "ready" }
Browser: opens WebSocket to ws://api/ws/{replId}
  → ReplSession starts: terminal stream + file watcher
  → Browser renders file tree + opens main file in Monaco
```

### Flow 2: User Types in Terminal

```
Browser (xterm.js): keypress "l" "s" "\r"
  → WS send: { type: "terminal_input", payload: { data: "ls\r" } }
  → TerminalManager: docker exec writes "ls\r" to container shell
  → Container executes "ls" → stdout: "src/ package.json ..."
  → TerminalManager: reads stdout stream
  → WS send: { type: "terminal_output", payload: { data: "src/  package.json\n" } }
  → Browser (xterm.js): renders output
```

### Flow 3: User Saves a File

```
Browser (Monaco): Ctrl+S on /src/App.tsx
  → WS send: { type: "file_save", payload: { path: "/src/App.tsx", content: "..." } }
  → FileManager: writes to Docker volume (instant)
  → FileManager: pushes to S3 in background (durable)
  → watchfiles: detects the change
  → WS send: { type: "file_update", payload: { path: "/src/App.tsx", action: "modified" } }
  → Browser: confirms save (green indicator)
```

### Flow 4: User Asks AI to Build Something

```
Browser (Chat): "Build a REST API with /users endpoint"
  → WS send: { type: "ai_prompt", payload: { message: "..." } }
  → AgentRunner.run() starts as asyncio task
  → Claude API called with tools + file tree context
  → Claude: "I'll look at the project structure first"
    → WS: { type: "ai_stream", payload: { chunk: "I'll look at..." } }
  → Claude calls list_files("/")
    → WS: { type: "agent_action", tool: "list_files", ... }
  → Claude calls write_file("/src/routes/users.py", "...")
    → FileManager writes file
    → WS: { type: "agent_action", tool: "write_file", path: "..." }
    → WS: { type: "file_update", path: "/src/routes/users.py" }
    → Monaco: refreshes file tree, shows new file
  → Claude calls run_command("python -m pytest")
    → WS: { type: "agent_action", tool: "run_command", ... }
    → terminal output streamed to xterm.js
  → Claude: "Done! I've created a REST API..."
    → WS: { type: "ai_done" }
```

---

## 11. Database Design

```sql
-- PostgreSQL schema

CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE repls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    stack           TEXT NOT NULL CHECK (stack IN ('react', 'nextjs', 'python')),
    container_id    TEXT,                           -- Docker container ID
    is_active       BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_active_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repl_id     UUID REFERENCES repls(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content     TEXT NOT NULL,
    tool_name   TEXT,                               -- if role = 'tool'
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Index for fast repl lookup
CREATE INDEX idx_repls_user ON repls(user_id);
CREATE INDEX idx_messages_repl ON messages(repl_id, created_at);
```

---

## 12. Project Structure

```
runner/
├── frontend/                          # React app
│   ├── src/
│   │   ├── components/
│   │   │   ├── Editor/
│   │   │   │   ├── MonacoEditor.tsx
│   │   │   │   └── FileExplorer.tsx
│   │   │   ├── Terminal/
│   │   │   │   └── Terminal.tsx
│   │   │   ├── Chat/
│   │   │   │   ├── ChatPanel.tsx
│   │   │   │   └── AgentAction.tsx
│   │   │   └── Preview/
│   │   │       └── PreviewFrame.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   ├── useTerminal.ts
│   │   │   └── useFileSystem.ts
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                           # FastAPI app
│   ├── main.py
│   ├── api/
│   │   ├── routes/
│   │   │   ├── repl.py
│   │   │   └── files.py
│   │   └── websocket/
│   │       ├── handler.py
│   │       └── protocol.py
│   ├── services/
│   │   ├── container_manager.py
│   │   ├── file_manager.py
│   │   ├── terminal_manager.py
│   │   └── agent_runner.py
│   ├── models/
│   │   ├── database.py
│   │   └── schemas.py
│   ├── core/
│   │   ├── config.py
│   │   └── s3.py
│   └── requirements.txt
│
├── docker_images/                     # Stack-specific images
│   ├── react/
│   │   ├── Dockerfile
│   │   └── template/                  # Starter React project
│   ├── nextjs/
│   │   ├── Dockerfile
│   │   └── template/
│   └── python/
│       ├── Dockerfile
│       └── template/
│
├── docker-compose.yml                 # Local dev: FastAPI + Postgres + Traefik
├── project_overview.md                # This file
└── README.md
```

---

## 13. Build Plan

### Phase 1 — Skeleton (Days 1-3)
- [ ] Set up FastAPI project with uvicorn
- [ ] Set up React project with Vite
- [ ] Basic WebSocket connection between frontend and backend
- [ ] Send and receive a simple message to prove WS works

### Phase 2 — Container + Terminal (Days 4-7)
- [ ] ContainerManager: create/start/stop Docker containers
- [ ] TerminalManager: `docker exec` with PTY, stream I/O
- [ ] xterm.js in React wired to terminal_output messages
- [ ] User can type commands, see output — **core loop works**

### Phase 3 — File System (Days 8-11)
- [ ] FileManager: read/write/list files in Docker volume
- [ ] FileExplorer in React: tree view of workspace files
- [ ] Monaco editor: open file → read content → edit → save
- [ ] File watcher: detect changes → notify browser

### Phase 4 — Persistence (Days 12-14)
- [ ] S3/R2 bucket setup
- [ ] Pull files from S3 on session start
- [ ] Push files to S3 on save (background)
- [ ] Stack templates stored in S3 (react starter, python starter)
- [ ] PostgreSQL: users, repls, messages tables

### Phase 5 — AI Agent (Days 15-20)
- [ ] Chat panel UI in React
- [ ] AgentRunner: Claude API with 4 tools
- [ ] Tool execution against real container
- [ ] Stream AI text + agent actions over WebSocket
- [ ] Monaco auto-refresh when AI writes a file

### Phase 6 — Polish (Days 21-25)
- [ ] Traefik preview URL routing
- [ ] Idle container cleanup (cron job)
- [ ] Error handling (container crash, WS disconnect)
- [ ] Auth (JWT or Clerk)
- [ ] UI polish: loading states, error toasts, responsive layout

---

## 14. Hard Problems & How I'd Solve Them

### Problem 1: Container Cold Start (2-5 seconds)

**Why it happens:** Pulling image + creating container + syncing files from S3.

**Solution:**
- Pre-pull all stack images on the host
- Keep a pool of "warm" containers ready (pre-created but unassigned)
- Show a loading animation in the browser during startup

### Problem 2: Terminal Emulation

**Why it's hard:** A real terminal (PTY) handles raw mode, colors (ANSI codes), cursor movement, Ctrl+C signals. Simple subprocess stdout doesn't do this.

**Solution:**
- Use `docker exec -it` with TTY mode
- The Docker SDK returns a raw socket — pipe it directly to xterm.js
- xterm.js handles all ANSI codes natively

### Problem 3: File Sync Conflicts

**What if:** AI writes a file at the same time user is editing it in Monaco?

**Solution:**
- When AI writes a file, send `file_update` to browser
- Browser shows a notification: "AI updated Login.tsx — reload?"
- Or: auto-reload if user hasn't made unsaved changes to that file
- For MVP: last-write-wins is fine

### Problem 4: Security — Running Untrusted Code

**Risk:** User runs `rm -rf /` or tries to escape the container.

**Solution:**
- Docker containers already provide isolation
- Resource limits (CPU, memory, disk)
- No root access inside container (run as non-root user)
- Network restrictions (no outbound to your infrastructure)
- For production: use gVisor or Firecracker for deeper isolation

### Problem 5: WebSocket Reconnection

**What if:** User's internet drops for 5 seconds.

**Solution:**
- Frontend: auto-reconnect with exponential backoff
- Backend: container is still alive (it doesn't depend on the WS)
- On reconnect: resend current file tree + terminal state
- xterm.js has a `reset()` method — clear and refill from server

---

## 15. Tech Stack Summary

| Component         | Technology                  |
|-------------------|-----------------------------|
| Frontend          | React + Vite                |
| Code Editor       | Monaco Editor               |
| Terminal          | xterm.js                    |
| Backend           | FastAPI (Python)            |
| WebSockets        | FastAPI native WebSocket    |
| Containers        | Docker (SDK for Python)     |
| File Storage      | Cloudflare R2 / AWS S3      |
| Database          | PostgreSQL + SQLAlchemy     |
| AI Model          | Claude claude-sonnet-4-5 (Anthropic) |
| Agent Framework   | None — raw tool calling     |
| Reverse Proxy     | Traefik                     |
| File Watching     | watchfiles (Python)         |
| Container Orchestration (prod) | Kubernetes     |

---

## References

- [hkirat/repl (GitHub)](https://github.com/hkirat/repl)
- [YouTube: Repl.it Beginner to Advance](https://youtu.be/s0kBqGpThp0)
- [Anthropic Tool Use Docs](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [FastAPI WebSocket Docs](https://fastapi.tiangolo.com/advanced/websockets/)
- [Docker SDK for Python](https://docker-py.readthedocs.io/)
- [Monaco Editor](https://microsoft.github.io/monaco-editor/)
- [xterm.js](https://xtermjs.org/)
- [e2b.dev](https://e2b.dev) — managed sandbox alternative
