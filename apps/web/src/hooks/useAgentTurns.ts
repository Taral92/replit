import { useState, useEffect, useCallback } from 'react';
import { Socket } from 'socket.io-client';

export interface TurnStep {
  id: string;
  tool: string;
  target: string;
  action: 'explored' | 'edited' | 'ran' | 'verified' | 'failed' | 'action';
  status: 'running' | 'completed' | 'failed';
  added?: number;
  removed?: number;
  diff?: string;
  count?: number;
  error?: string;
  timestamp?: number;
}

export interface AgentTurn {
  turn_id: string;
  prompt?: string;
  started_at: number;
  ended_at: number | null;
  isWorking: boolean;
  status?: string;
  steps: TurnStep[];
}

export function useAgentTurns(socket: Socket | null) {
  const [turns, setTurns] = useState<Record<string, AgentTurn>>({});
  const [turnOrder, setTurnOrder] = useState<string[]>([]);

  useEffect(() => {
    if (!socket) return;

    // 1. Turn Start
    const handleTurnStart = (data: { turn_id: string; started_at: number; prompt?: string }) => {
      const { turn_id, started_at, prompt } = data;
      setTurns(prev => {
        if (prev[turn_id]) return prev;
        return {
          ...prev,
          [turn_id]: {
            turn_id,
            prompt,
            started_at: started_at || Date.now(),
            ended_at: null,
            isWorking: true,
            steps: []
          }
        };
      });

      setTurnOrder(prev => prev.includes(turn_id) ? prev : [...prev, turn_id]);
    };

    // 2. Step / Tool Execution
    const handleStep = (stepPayload: any) => {
      const { turn_id, tool, target, action, status, added, removed, diff, error } = stepPayload;
      if (!turn_id) return;

      setTurns(prev => {
        const turn = prev[turn_id] || {
          turn_id,
          started_at: Date.now(),
          ended_at: null,
          isWorking: true,
          steps: []
        };

        const existingSteps = [...turn.steps];
        const stepAction = error ? 'failed' : action || (tool === 'run_command' ? 'ran' : tool in ['write_file', 'patch_file'] ? 'edited' : 'explored');

        // Deduplicate repeated reads of the same file
        if (stepAction === 'explored') {
          const existingIdx = existingSteps.findIndex(s => s.target === target && s.action === 'explored');
          if (existingIdx >= 0) {
            existingSteps[existingIdx] = {
              ...existingSteps[existingIdx],
              count: (existingSteps[existingIdx].count || 1) + 1,
              status: status || 'completed'
            };
          } else {
            existingSteps.push({
              id: `${tool}_${target}_${Date.now()}`,
              tool,
              target,
              action: 'explored',
              status: status || 'completed',
              count: 1
            });
          }
        } else if (stepAction === 'edited') {
          // File edit with line diffs
          const existingIdx = existingSteps.findIndex(s => s.target === target && s.action === 'edited');
          if (existingIdx >= 0) {
            existingSteps[existingIdx] = {
              ...existingSteps[existingIdx],
              added: added !== undefined ? added : existingSteps[existingIdx].added,
              removed: removed !== undefined ? removed : existingSteps[existingIdx].removed,
              diff: diff || existingSteps[existingIdx].diff,
              status: status || 'completed'
            };
          } else {
            existingSteps.push({
              id: `${tool}_${target}_${Date.now()}`,
              tool,
              target,
              action: 'edited',
              status: status || 'completed',
              added: added || 0,
              removed: removed || 0,
              diff: diff || ''
            });
          }
        } else {
          // Command execution / verification / failed
          existingSteps.push({
            id: `${tool}_${Date.now()}`,
            tool,
            target,
            action: stepAction,
            status: status || (error ? 'failed' : 'completed'),
            error
          });
        }

        return {
          ...prev,
          [turn_id]: {
            ...turn,
            steps: existingSteps
          }
        };
      });
    };

    // 3. Turn End
    const handleTurnEnd = (data: { turn_id: string; ended_at: number }) => {
      const { turn_id, ended_at } = data;
      if (!turn_id) return;

      setTurns(prev => {
        const turn = prev[turn_id];
        if (!turn) return prev;

        return {
          ...prev,
          [turn_id]: {
            ...turn,
            ended_at: ended_at || Date.now(),
            isWorking: false
          }
        };
      });
    };

    const handleAgentStatus = (data: { turn_id: string; status: string }) => {
      const { turn_id, status } = data;
      if (!turn_id) return;

      setTurns(prev => {
        const turn = prev[turn_id];
        if (!turn) return prev;
        return {
          ...prev,
          [turn_id]: { ...turn, status }
        };
      });
    };

    socket.on('agent.turn.started', handleTurnStart);
    socket.on('agent.step', handleStep);
    socket.on('agent.tool.completed', handleStep);
    socket.on('agent.turn.completed', handleTurnEnd);
    socket.on('agent.status', handleAgentStatus);

    return () => {
      socket.off('agent.turn.started', handleTurnStart);
      socket.off('agent.step', handleStep);
      socket.off('agent.tool.completed', handleStep);
      socket.off('agent.turn.completed', handleTurnEnd);
      socket.off('agent.status', handleAgentStatus);
    };
  }, [socket]);

  const clearTurns = useCallback(() => {
    setTurns({});
    setTurnOrder([]);
  }, []);

  return { turns, turnOrder, clearTurns };
}
