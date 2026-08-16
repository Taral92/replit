import { create } from 'zustand';

export interface ToolCallArgs {
  path?: string;
  command?: string;
  query?: string;
  [key: string]: any;
}

export interface AgentStep {
  tool: string;
  target: string;
  action: string;
  type: string;
  status: 'running' | 'completed' | 'error';
  args?: ToolCallArgs;
  added?: number;
  removed?: number;
  diff?: string;
  startTimestamp: number;
  endTimestamp?: number;
}

export interface AgentTurn {
  id: string;
  startedAt: number;
  endedAt?: number;
  durationMs?: number;
  prompt: string;
  status: string;
  message: string;
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
  addStep: (turnId: string, step: Omit<AgentStep, 'endTimestamp'>) => void;
  completeStep: (turnId: string, tool: string, target: string, result: Partial<AgentStep>) => void;
  completeTurn: (turnId: string, data: { endedAt: number; durationMs: number; error?: string }) => void;
  
  setSessions: (sessions: { id: string; name: string }[]) => void;
  setActiveSession: (id: string) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  turns: [],
  activeTurnId: null,
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

  addStep: (turnId, step) => set((state) => ({
    turns: state.turns.map(t => {
      if (t.id !== turnId) return t;
      return { ...t, steps: [...t.steps, step] };
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
    turns: state.turns.map(t => 
      t.id === turnId ? { ...t, ...data, activeTurnId: null } : t
    ),
    activeTurnId: state.activeTurnId === turnId ? null : state.activeTurnId
  })),

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (id) => set({ activeSessionId: id })
}));
