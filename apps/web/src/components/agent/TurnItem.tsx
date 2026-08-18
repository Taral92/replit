import React from 'react';
import { AgentTurn } from '../../store/useAgentStore';
import { ThinkingIndicator } from './ThinkingIndicator';
import { ToolCallRow } from './ToolCallRow';
import { MessageBlock } from './MessageBlock';
import { PlanChecklist } from './PlanChecklist';
import { User } from 'lucide-react';

export const TurnItem: React.FC<{ turn: AgentTurn }> = ({ turn }) => {
  const isCompleted = !!turn.endedAt;
  const isRunning = !isCompleted;
  
  // Basic stats for footer
  const filesChanged = new Set(turn.steps.filter(s => s.action === 'edited').map(s => s.target)).size;
  const formatTime = (ms?: number) => ms ? `${(ms / 1000).toFixed(1)}s` : '';

  // Rolls a batch of tool calls into one scannable sentence — "Ran 2 commands,
  // read 3 files". The point of the panel is that you can read what happened
  // without expanding anything.
  const summarize = (steps: typeof turn.steps): string => {
    const commands = steps.filter(s => ['shell', 'run_command', 'list_processes'].includes(s.tool)).length;
    const reads = steps.filter(s => ['read_file', 'list_dir', 'search'].includes(s.tool)).length;
    const edits = new Set(
      steps.filter(s => ['write_file', 'edit_file', 'patch_file'].includes(s.tool)).map(s => s.target)
    ).size;

    const parts: string[] = [];
    const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? 's' : ''}`;
    if (commands) parts.push(`Ran ${plural(commands, 'command')}`);
    if (reads) parts.push(`read ${plural(reads, 'file')}`);
    if (edits) parts.push(`edited ${plural(edits, 'file')}`);

    if (!parts.length) return '';
    // Sentence-case the first fragment only, so it reads as prose.
    return parts.join(', ').replace(/^./, c => c.toUpperCase());
  };

  // Group steps by planStepId
  const groups: Record<string, typeof turn.steps> = {};
  const ungrouped: typeof turn.steps = [];

  turn.steps.forEach(step => {
    if (step.planStepId) {
      if (!groups[step.planStepId]) groups[step.planStepId] = [];
      groups[step.planStepId].push(step);
    } else {
      ungrouped.push(step);
    }
  });

  return (
    <div className="flex flex-col gap-2 mb-6">
      <div className="pl-[12px] border-l-2 border-border-subtle flex flex-col gap-2">
        {/* User Prompt */}
        <div>
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

        {/* Plan Checklist */}
        {turn.plan && turn.plan.length > 0 && (
          <PlanChecklist plan={turn.plan} />
        )}

        {/* Agent Thinking State */}
        {isRunning && (
          <ThinkingIndicator status={turn.status} />
        )}

        {/* Ungrouped Steps */}
        {ungrouped.length > 0 && (
          <div className="flex flex-col">
            {summarize(ungrouped) && (
              <div className="text-sm text-text-secondary mb-1">{summarize(ungrouped)}</div>
            )}
            {ungrouped.map((step, idx) => (
              <ToolCallRow key={`${step.startTimestamp}-${idx}`} step={step} />
            ))}
          </div>
        )}

        {/* Grouped Steps */}
        {Object.entries(groups).map(([planStepId, steps]) => {
          const planStep = turn.plan?.find(p => p.id === planStepId);
          return (
            <div key={planStepId} className="flex flex-col mt-2">
              {planStep && (
                <div className="flex items-baseline justify-between mb-1 gap-3">
                  <span className="text-xs font-medium text-text-secondary truncate">
                    ↳ {planStep.title}
                  </span>
                  {summarize(steps) && (
                    <span className="text-xs text-text-tertiary shrink-0">{summarize(steps)}</span>
                  )}
                </div>
              )}
              {steps.map((step, idx) => (
                <ToolCallRow key={`${step.startTimestamp}-${idx}`} step={step} />
              ))}
            </div>
          );
        })}

        {/* Agent Message */}
        <MessageBlock content={turn.message} isStreaming={isRunning && turn.message.length > 0} />

        {/* Footer (when complete) */}
        {isCompleted && (
          <div className="mt-2 pt-2">
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
          <div className="mt-2">
            <div className="text-sm text-danger font-mono bg-danger-muted p-2 rounded">
              {turn.error}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
