import { ChildProcess, spawn } from 'child_process';
import { EventEmitter } from 'events';

export type ProcessStatus = 'STARTING' | 'RUNNING' | 'STOPPED' | 'FAILED';

export interface ProcessState {
  processId: string;
  command: string;
  cwd: string;
  pid?: number;
  status: ProcessStatus;
  startedAt: string;
  exitCode?: number | null;
  ports: string[];
  logs: string[];
}

export class ProcessManager extends EventEmitter {
  private processes = new Map<string, { proc: ChildProcess; state: ProcessState }>();
  private activePorts = new Set<string>();

  constructor() {
    super();
  }

  startProcess(processId: string, command: string, cwd: string): ProcessState {
    // If processId already exists and is running, stop it first
    if (this.processes.has(processId)) {
      this.stopProcess(processId);
    }

    const state: ProcessState = {
      processId,
      command,
      cwd,
      status: 'STARTING',
      startedAt: new Date().toISOString(),
      ports: [],
      logs: [],
    };

    const env = {
      ...process.env,
      CI: 'true',
      TERM: 'xterm-256color',
    };

    const proc = spawn(command, {
      shell: true,
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    state.pid = proc.pid;
    state.status = 'RUNNING';

    const portRegex = /(?:https?:\/\/(?:localhost|127\.0\.0\.1):|port\s+)(\d{4,5})/gi;

    const handleOutput = (data: Buffer) => {
      const text = data.toString('utf-8');
      state.logs.push(text);
      if (state.logs.length > 200) state.logs.shift(); // Keep last 200 log chunks

      // Detect active listening ports
      let match;
      while ((match = portRegex.exec(text)) !== null) {
        const port = match[1];
        if (port !== '8000' && port !== '5173') {
          if (!state.ports.includes(port)) {
            state.ports.push(port);
          }
          if (!this.activePorts.has(port)) {
            this.activePorts.add(port);
            this.emit('port:detected', { port, processId });
          }
        }
      }

      this.emit('process:log', { processId, data: text });
    };

    proc.stdout?.on('data', handleOutput);
    proc.stderr?.on('data', handleOutput);

    proc.on('close', (code) => {
      state.status = code === 0 ? 'STOPPED' : 'FAILED';
      state.exitCode = code;
      // Remove any ports this process was listening on
      state.ports.forEach((p) => this.activePorts.delete(p));
      this.emit('process:exited', { processId, exitCode: code });
    });

    this.processes.set(processId, { proc, state });
    this.emit('process:started', state);
    return state;
  }

  stopProcess(processId: string): boolean {
    const item = this.processes.get(processId);
    if (!item) return false;

    try {
      item.proc.kill('SIGTERM');
      setTimeout(() => {
        if (item.state.status === 'RUNNING') {
          item.proc.kill('SIGKILL');
        }
      }, 3000);
      item.state.status = 'STOPPED';
      return true;
    } catch {
      return false;
    }
  }

  getProcess(processId: string): ProcessState | undefined {
    return this.processes.get(processId)?.state;
  }

  listProcesses(): ProcessState[] {
    return Array.from(this.processes.values()).map((p) => p.state);
  }

  getActivePorts(): string[] {
    return Array.from(this.activePorts);
  }

  cleanup() {
    for (const [id] of this.processes) {
      this.stopProcess(id);
    }
  }
}
