import React from 'react';
import { AgentTurn } from '../../store/useAgentStore';
import { ThinkingIndicator } from './ThinkingIndicator';
import { ToolCallRow } from './ToolCallRow';
import { MessageBlock } from './MessageBlock';
import { User } from 'lucide-react';

export const TurnItem: React.FC<{ turn: AgentTurn }> = ({ turn }) => {
  const isCompleted = !!turn.endedAt;
  const isRunning = !isCompleted;
  
  // Basic stats for footer
  const filesChanged = new Set(turn.steps.filter(s => s.action === 'edited').map(s => s.target)).size;
  const formatTime = (ms?: number) => ms ? `${(ms / 1000).toFixed(1)}s` : '';

  return (
    <div className="flex flex-col gap-2 mb-6">
      {/* User Prompt */}
      <div className="pl-[12px] border-l-2 border-border-subtle">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-1.5 text-xs font-medium text-text-tertiary uppercase tracking-wide">
            <User size={12} />
            <span>You</span>
          </div>
          <span className="text-2xs text-text-tertiary">
            {new Date(turn.startedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        <div className="text-base text-text-primary mb-2">
          {turn.prompt}
        </div>
      </div>

      {/* Agent Thinking State */}
      {isRunning && turn.status === 'Thinking...' && (
        <ThinkingIndicator />
      )}

      {/* Steps / Tool Calls */}
      <div className="flex flex-col">
        {turn.steps.map((step, idx) => (
          <ToolCallRow key={`${step.startTimestamp}-${idx}`} step={step} />
        ))}
      </div>

      {/* Agent Message */}
      <MessageBlock content={turn.message} isStreaming={isRunning && turn.message.length > 0} />

      {/* Footer (when complete) */}
      {isCompleted && (
        <div className="pl-[12px] border-l-2 border-border-subtle mt-2 pt-2">
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            {filesChanged > 0 && <span>{filesChanged} file{filesChanged > 1 ? 's' : ''} changed</span>}
            {filesChanged > 0 && <span>·</span>}
            <span>{formatTime(turn.durationMs)}</span>
            {filesChanged > 0 && (
              <>
                <span>·</span>
                <button className="hover:text-text-primary transition-colors cursor-pointer flex items-center gap-1">
                  <span className="text-md">⧉</span> Review diff
                </button>
              </>
            )}
          </div>
        </div>
      )}
      
      {/* Error state */}
      {isCompleted && turn.error && (
        <div className="pl-[12px] border-l-2 border-danger-muted mt-2">
          <div className="text-sm text-danger font-mono bg-danger-muted p-2 rounded">
            {turn.error}
          </div>
        </div>
      )}
    </div>
  );
};
