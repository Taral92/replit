import { useEffect, useRef } from 'react';
import { Socket } from 'socket.io-client';
import { useAgentStore } from '../store/useAgentStore';

export const useSocketBridge = (socket: Socket | null) => {
  const isRegistered = useRef(false);
  
  const { 
    addTurn, 
    appendMessage, 
    updateStatus, 
    updatePlan,
    addStep,
    stepProgress,
    setPendingQuestion,
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

    const onPlanUpdated = (data: { turn_id: string; plan: any[] }) => {
      updatePlan(data.turn_id, data.plan);
    };

    const onStep = (data: {
      turn_id: string;
      tool: string;
      target: string;
      action: string;
      type: string;
      status: string;
      args: Record<string, any>;
      plan_step_id?: string;
      timestamp: number;
    }) => {
      addStep(data.turn_id, {
        tool: data.tool,
        target: data.target,
        action: data.action,
        type: data.type,
        status: 'running',
        args: data.args,
        planStepId: data.plan_step_id,
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

    // Emitted ~4/sec while a tool is in flight. The backend has been sending
    // these since 6A; nothing was listening, which is why long tools rendered
    // as a frozen row.
    const onStepProgress = (data: {
      turn_id: string;
      target: string;
      phase: string;
    }) => {
      stepProgress(data.turn_id, data.target, data.phase);
    };

    // The agent is parked on a Future server-side while this is unanswered.
    const onQuestion = (data: {
      interaction_id: string; kind: string; question: string; options: string[];
    }) => {
      setPendingQuestion({
        interactionId: data.interaction_id,
        kind: data.kind,
        question: data.question,
        options: data.options || [],
      });
    };

    socket.on('agent.question', onQuestion);
    socket.on('agent.turn.started', onTurnStarted);
    socket.on('agent.step.progress', onStepProgress);
    socket.on('agent.message', onMessage);
    socket.on('agent.status', onStatus);
    socket.on('agent.plan.updated', onPlanUpdated);
    socket.on('agent.step', onStep);
    socket.on('agent.tool.completed', onToolCompleted);
    socket.on('agent.turn.completed', onTurnCompleted);

    return () => {
      socket.off('agent.question', onQuestion);
      socket.off('agent.turn.started', onTurnStarted);
      socket.off('agent.step.progress', onStepProgress);
      socket.off('agent.message', onMessage);
      socket.off('agent.status', onStatus);
      socket.off('agent.plan.updated', onPlanUpdated);
      socket.off('agent.step', onStep);
      socket.off('agent.tool.completed', onToolCompleted);
      socket.off('agent.turn.completed', onTurnCompleted);
      isRegistered.current = false;
    };
  }, [socket, addTurn, appendMessage, updateStatus, updatePlan, addStep, completeStep, completeTurn]);
};
