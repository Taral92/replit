import { spawn } from 'child_process';
import cors from 'cors';
import dotenv from 'dotenv';
import express, { Request, Response } from 'express';
import fs from 'fs';
import { createServer } from 'http';
import path from 'path';
import { WebSocket, WebSocketServer } from 'ws';
import { ProcessManager } from './process_manager';
import { createWorkspaceSnapshot, restoreWorkspaceSnapshot } from './s3_snapshots';

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

const httpServer = createServer(app);
const wss = new WebSocketServer({ server: httpServer, path: '/v1/terminal' });

const BASE_WORKSPACE = process.env.WORKDIR || path.join(process.cwd(), '../workspace');
if (!fs.existsSync(BASE_WORKSPACE)) {
  fs.mkdirSync(BASE_WORKSPACE, { recursive: true });
}

const processManager = new ProcessManager();

// Helper to resolve and validate workspace path
function resolveWorkspace(workspaceId: string = 'default'): string {
  const cleanId = workspaceId.replace(/[^a-zA-Z0-9_-]/g, '');
  const dir = cleanId === 'default' ? BASE_WORKSPACE : path.join(BASE_WORKSPACE, cleanId);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

function resolveFilePath(workspaceDir: string, relativePath: string): string | null {
  const cleanRel = relativePath.replace(/^\/+/, '');
  const fullPath = path.resolve(workspaceDir, cleanRel);
  if (!fullPath.startsWith(path.resolve(workspaceDir))) {
    return null; // Path traversal detected
  }
  return fullPath;
}

// --- Health & Readiness Endpoints for Kubernetes ---
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.get('/ready', (req: Request, res: Response) => {
  res.json({ ready: true, uptime: process.uptime() });
});

// --- Filesystem REST API ---
function getFilesTree(dir: string, baseDir: string): any[] {
  const results: any[] = [];
  const ignored = new Set(['node_modules', '.git', '.next', 'dist', 'build', '__pycache__']);
  try {
    const list = fs.readdirSync(dir);
    for (const file of list) {
      if (ignored.has(file) || file.startsWith('.')) continue;
      const full = path.join(dir, file);
      const stat = fs.statSync(full);
      const rel = path.relative(baseDir, full);
      if (stat.isDirectory()) {
        results.push({
          name: file,
          type: 'directory',
          path: rel,
          children: getFilesTree(full, baseDir),
        });
      } else {
        results.push({
          name: file,
          type: 'file',
          path: rel,
          size: stat.size,
        });
      }
    }
  } catch {}
  return results;
}

app.get('/v1/workspaces/:id/files', (req: Request, res: Response) => {
  const wsDir = resolveWorkspace(req.params.id);
  const tree = getFilesTree(wsDir, wsDir);
  res.json(tree);
});

app.get('/v1/workspaces/:id/files/content', (req: Request, res: Response) => {
  const wsDir = resolveWorkspace(req.params.id);
  const target = resolveFilePath(wsDir, (req.query.path as string) || '');
  if (!target) return res.status(400).json({ error: 'Path traversal denied' });
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    return res.status(404).json({ error: 'File not found' });
  }
  const content = fs.readFileSync(target, 'utf-8');
  res.send(content);
});

app.put('/v1/workspaces/:id/files/content', (req: Request, res: Response) => {
  const wsDir = resolveWorkspace(req.params.id);
  const target = resolveFilePath(wsDir, req.body.path || '');
  if (!target) return res.status(400).json({ error: 'Path traversal denied' });
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, req.body.content || '', 'utf-8');
  res.json({ success: true, path: req.body.path });
});

// --- Command Execution & Process API ---
app.post('/v1/workspaces/:id/exec', async (req: Request, res: Response) => {
  const wsDir = resolveWorkspace(req.params.id);
  const { command, timeout = 30000 } = req.body;
  if (!command) return res.status(400).json({ error: 'Missing command' });

  const env = { ...process.env, CI: 'true', TERM: 'xterm-256color' };
  const child = spawn(command, { shell: true, cwd: wsDir, env });

  let stdout = '';
  let stderr = '';

  child.stdout?.on('data', (d) => (stdout += d.toString('utf-8')));
  child.stderr?.on('data', (d) => (stderr += d.toString('utf-8')));

  const timer = setTimeout(() => {
    child.kill('SIGKILL');
  }, timeout);

  child.on('close', (code) => {
    clearTimeout(timer);
    res.json({
      success: code === 0,
      exitCode: code,
      stdout: stdout.slice(-10000),
      stderr: stderr.slice(-10000),
    });
  });
});

app.post('/v1/workspaces/:id/processes', (req: Request, res: Response) => {
  const wsDir = resolveWorkspace(req.params.id);
  const { processId, command } = req.body;
  const proc = processManager.startProcess(processId || `proc-${Date.now()}`, command, wsDir);
  res.json(proc);
});

app.get('/v1/workspaces/:id/processes', (req: Request, res: Response) => {
  res.json(processManager.listProcesses());
});

app.delete('/v1/workspaces/:id/processes/:procId', (req: Request, res: Response) => {
  const stopped = processManager.stopProcess(req.params.procId);
  res.json({ success: stopped });
});

app.get('/v1/workspaces/:id/ports', (req: Request, res: Response) => {
  res.json({ ports: processManager.getActivePorts() });
});

// --- Snapshot Checkpoint API ---
app.post('/v1/workspaces/:id/snapshots', async (req: Request, res: Response) => {
  const wsDir = resolveWorkspace(req.params.id);
  const { projectId, snapshotId } = req.body;
  const result = await createWorkspaceSnapshot(wsDir, projectId || req.params.id, snapshotId || `snap-${Date.now()}`);
  res.json(result);
});

app.post('/v1/workspaces/:id/snapshots/restore', async (req: Request, res: Response) => {
  const wsDir = resolveWorkspace(req.params.id);
  const { projectId, snapshotId } = req.body;
  const result = await restoreWorkspaceSnapshot(wsDir, projectId || req.params.id, snapshotId);
  res.json(result);
});

// --- Scoped WebSocket Terminal (PTY Session) ---
wss.on('connection', (ws: WebSocket, req) => {
  const url = new URL(req.url || '', `http://${req.headers.host}`);
  const workspaceId = url.searchParams.get('workspace_id') || 'default';
  const wsDir = resolveWorkspace(workspaceId);

  const shell = process.env.SHELL || '/bin/bash';
  // Allocate PTY using Python's pty module on the host/container
  const ptyProcess = spawn(
    'python3',
    ['-c', `import pty, os; os.chdir('${wsDir}'); pty.spawn('${shell}')`],
    {
      cwd: wsDir,
      env: { ...process.env, TERM: 'xterm-256color' },
    }
  );

  ptyProcess.stdout.on('data', (data: Buffer) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'terminal.output', data: data.toString('utf-8') }));
    }
  });

  ptyProcess.stderr.on('data', (data: Buffer) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'terminal.output', data: data.toString('utf-8') }));
    }
  });

  ws.on('message', (message: string) => {
    try {
      const parsed = JSON.parse(message);
      if (parsed.type === 'terminal.input' && parsed.data) {
        ptyProcess.stdin.write(parsed.data);
      }
    } catch {
      // Raw string fallback
      ptyProcess.stdin.write(message.toString());
    }
  });

  ws.on('close', () => {
    ptyProcess.kill();
  });
});

const PORT = process.env.PORT || 3000;
httpServer.listen(PORT, () => {
  console.log(`[RunnerService] Hardened Runner listening on port ${PORT}`);
});
