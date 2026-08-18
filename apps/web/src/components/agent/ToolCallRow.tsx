import React, { useState } from 'react';
import { ChevronRight, ChevronDown, Terminal, FileCode, Search, CheckCircle2, XCircle, RotateCcw } from 'lucide-react';
import { AgentStep } from '../../store/useAgentStore';
import { Button } from '../ui/Button';

export const ToolCallRow: React.FC<{ step: AgentStep; onRetry?: () => void }> = ({ step, onRetry }) => {
  const [expanded, setExpanded] = useState(false);
  
  const isError = step.status === 'error';
  const Icon = ['shell', 'run_command'].includes(step.tool) ? Terminal : step.tool === 'search' ? Search : FileCode;
  
  const getVerb = () => {
    const isCompleted = step.status === 'completed';
    if (['write_file', 'patch_file', 'edit_file'].includes(step.tool)) {
      return isCompleted ? 'edited' : 'editing';
    }
    if (['shell', 'run_command', 'list_processes'].includes(step.tool)) {
      return isCompleted ? 'ran' : 'running';
    }
    if (['read_file', 'list_dir', 'search'].includes(step.tool)) {
      return isCompleted ? 'read' : 'reading';
    }
    return isCompleted ? 'completed' : 'running';
  };
  
  if (isError) {
    return (
      <div className="flex flex-col gap-2 p-3 mt-1 mb-2 rounded-md bg-danger-muted border border-danger/20">
        <div className="flex items-center gap-2 text-danger">
          <XCircle size={14} />
          <span className="text-base font-medium">Tool Execution Failed</span>
        </div>
        <div className="text-xs font-mono text-danger/80 bg-danger/10 p-2 rounded truncate">
          {step.args?.command || step.args?.path || 'Unknown command'}
        </div>
        {onRetry && (
          <div className="mt-1">
            <Button variant="danger" size="sm" onClick={onRetry} className="h-6 text-xs px-2">
              <RotateCcw size={12} className="mr-1" />
              Retry
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col border-l-2 border-border-subtle pl-[12px]">
      <div 
        className="flex items-center h-[24px] cursor-pointer group hover:bg-surface-2 -ml-[12px] pl-[12px] pr-2 rounded-r"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown size={14} className="text-text-tertiary mr-1.5" />
        ) : (
          <ChevronRight size={14} className="text-text-tertiary mr-1.5" />
        )}
        <Icon size={14} className="text-text-secondary mr-2" />
        <span className="text-sm font-medium text-text-primary capitalize mr-2">{getVerb()}</span>
        <span className="text-sm font-mono text-text-tertiary truncate flex-1">
          {step.target}
          {/* Animated ellipsis while in flight. This is what makes a 40-second
              npm install read as working rather than hung. */}
          {step.status === 'running' && (
            <span className="inline-block w-4 text-left text-text-tertiary">
              <span className="animate-ellipsis">…</span>
            </span>
          )}
        </span>


        {step.status === 'completed' && (
          <div className="flex items-center text-success ml-2">
            {step.added !== undefined && step.added > 0 && <span className="text-xs mr-1.5">+{step.added}</span>}
            {step.removed !== undefined && step.removed > 0 && <span className="text-xs mr-1.5 text-danger">-{step.removed}</span>}
            <CheckCircle2 size={14} />
          </div>
        )}
        {step.status === 'running' && (
          <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse ml-2" />
        )}
      </div>
      
      {expanded && step.diff && (
        <div className="mt-2 mb-2 pr-2">
          {/* We'll render DiffCard here, for now raw diff text */}
          <div className="text-xs font-mono whitespace-pre bg-surface-2 p-2 rounded text-text-secondary overflow-x-auto border border-border-subtle">
            {step.diff}
          </div>
        </div>
      )}
    </div>
  );
};
