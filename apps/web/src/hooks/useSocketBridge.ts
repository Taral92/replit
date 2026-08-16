import { useEffect, useRef } from 'react';
import { Socket } from 'socket.io-client';
import { useAgentStore } from '../store/useAgentStore';

export const useSocketBridge = (socket: Socket | null) => {
  const isRegistered = useRef(false);
  
  const { 
    addTurn, 
    appendMessage, 
    updateStatus, 
    addStep, 
    completeStep, 
    completeTurn 
  } = useAgentStore();

  useEffect(() => {
    if (!socket || isRegistered.current) return;
    isRegistered.current = true;

    const onTurnStarted = (data: { turn_id: string; started_at: number; prompt: string }) => {
      addTurn({
        id: data.turn_id,
        startedAt: data.started_at,
        prompt: data.prompt,
        status: 'Thinking...',
        message: '',
        steps: []
      });
    };

    const onMessage = (data: { turn_id: string; content: string }) => {
      appendMessage(data.turn_id, data.content);
    };

    const onStatus = (data: { turn_id: string; status: string }) => {
      updateStatus(data.turn_id, data.status);
    };

    const onStep = (data: {
      turn_id: string;
      tool: string;
      target: string;
      action: string;
      type: string;
      status: string;
      args: Record<string, any>;
      timestamp: number;
    }) => {
      addStep(data.turn_id, {
        tool: data.tool,
        target: data.target,
        action: data.action,
        type: data.type,
        status: 'running',
        args: data.args,
        startTimestamp: data.timestamp
      });
    };

    const onToolCompleted = (data: {
      turn_id: string;
      tool: string;
      file: string;
      target: string;
      action: string;
      type: string;
      added: number;
      removed: number;
      diff: string;
      status: string;
      timestamp: number;
    }) => {
      completeStep(data.turn_id, data.tool, data.target, {
        added: data.added,
        removed: data.removed,
        diff: data.diff,
        endTimestamp: data.timestamp
      });
    };

    const onTurnCompleted = (data: {
      turn_id: string;
      started_at: number;
      ended_at: number;
      duration_ms: number;
      error?: string;
    }) => {
      completeTurn(data.turn_id, {
        endedAt: data.ended_at,
        durationMs: data.duration_ms,
        error: data.error
      });
    };

    socket.on('agent.turn.started', onTurnStarted);
    socket.on('agent.message', onMessage);
    socket.on('agent.status', onStatus);
    socket.on('agent.step', onStep);
    socket.on('agent.tool.completed', onToolCompleted);
    socket.on('agent.turn.completed', onTurnCompleted);

    return () => {
      socket.off('agent.turn.started', onTurnStarted);
      socket.off('agent.message', onMessage);
      socket.off('agent.status', onStatus);
      socket.off('agent.step', onStep);
      socket.off('agent.tool.completed', onToolCompleted);
      socket.off('agent.turn.completed', onTurnCompleted);
      isRegistered.current = false;
    };
  }, [socket, addTurn, appendMessage, updateStatus, addStep, completeStep, completeTurn]);
};
