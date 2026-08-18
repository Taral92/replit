import { create } from 'zustand';

export interface ToolCallArgs {
  path?: string;
  command?: string;
  query?: string;
  [key: string]: any;
}

export interface PlanStep {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
}

export interface AgentStep {
  tool: string;
  target: string;
  action: string;
  type: string;
  status: 'running' | 'completed' | 'error';
  args?: ToolCallArgs;
  planStepId?: string;
  added?: number;
  removed?: number;
  diff?: string;
  startTimestamp: number;
  endTimestamp?: number;
  // Live phase from agent.step.progress — "writing" | "running" | "reading".
  // Without this a 40-second npm install renders as a frozen row.
  phase?: string;
  lastProgressAt?: number;
}

export interface PendingQuestion {
  interactionId: string;
  kind: string;
  question: string;
  options: string[];
}

export interface AgentTurn {
  id: string;
  startedAt: number;
  endedAt?: number;
  durationMs?: number;
  prompt: string;
  status: string;
  message: string;
  plan?: PlanStep[];
  steps: AgentStep[];
  error?: string;
}

interface AgentState {
  turns: AgentTurn[];
  activeTurnId: string | null;
  sessions: { id: string; name: string }[];
  activeSessionId: string | null;
  
  // Actions
  addTurn: (turn: AgentTurn) => void;
  appendMessage: (turnId: string, chunk: string) => void;
  updateStatus: (turnId: string, status: string) => void;
  pendingQuestion: PendingQuestion | null;
  setPendingQuestion: (q: PendingQuestion | null) => void;
  updatePlan: (turnId: string, plan: PlanStep[]) => void;
  addStep: (turnId: string, step: Omit<AgentStep, 'endTimestamp'>) => void;
  stepProgress: (turnId: string, target: string, phase: string) => void;
  completeStep: (turnId: string, tool: string, target: string, result: Partial<AgentStep>) => void;
  completeTurn: (turnId: string, data: { endedAt: number; durationMs: number; error?: string }) => void;
  
  setSessions: (sessions: { id: string; name: string }[]) => void;
  setActiveSession: (id: string) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  turns: [],
  activeTurnId: null,
  pendingQuestion: null,
  sessions: [{ id: 'default', name: 'Current Session' }],
  activeSessionId: 'default',

  addTurn: (turn) => set((state) => {
    // Prevent duplicate turns
    if (state.turns.find(t => t.id === turn.id)) return state;
    return {
      turns: [...state.turns, turn],
      activeTurnId: turn.id
    };
  }),

  appendMessage: (turnId, chunk) => set((state) => ({
    turns: state.turns.map(t => 
      t.id === turnId ? { ...t, message: t.message + chunk } : t
    )
  })),

  updateStatus: (turnId, status) => set((state) => ({
    turns: state.turns.map(t => 
      t.id === turnId ? { ...t, status } : t
    )
  })),

  setPendingQuestion: (q) => set({ pendingQuestion: q }),

  updatePlan: (turnId, plan) => set((state) => ({
    turns: state.turns.map(t => 
      t.id === turnId ? { ...t, plan } : t
    )
  })),

  addStep: (turnId, step) => set((state) => ({
    turns: state.turns.map(t => {
      if (t.id !== turnId) return t;
      return { ...t, steps: [...t.steps, step] };
    })
  })),

  // Progress ticks arrive ~4/sec while a tool is in flight. They only touch the
  // still-running step, so completed rows stay frozen.
  stepProgress: (turnId, target, phase) => set((state) => ({
    turns: state.turns.map(t => {
      if (t.id !== turnId) return t;
      return {
        ...t,
        steps: t.steps.map(s =>
          s.target === target && s.status === 'running'
            ? { ...s, phase, lastProgressAt: Date.now() }
            : s
        ),
      };
    })
  })),

  completeStep: (turnId, tool, target, result) => set((state) => ({
    turns: state.turns.map(t => {
      if (t.id !== turnId) return t;
      
      const steps = [...t.steps];
      // Find the last running step matching tool and target
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].tool === tool && steps[i].target === target && steps[i].status === 'running') {
          steps[i] = { ...steps[i], ...result, status: 'completed' as const };
          break;
        }
      }
      return { ...t, steps };
    })
  })),

  completeTurn: (turnId, data) => set((state) => ({
    pendingQuestion: null,
    turns: state.turns.map(t => 
      t.id === turnId ? { ...t, ...data } : t
    ),
    activeTurnId: state.activeTurnId === turnId ? null : state.activeTurnId
  })),

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (id) => set({ activeSessionId: id })
}));
