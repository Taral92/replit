import React, { useRef, useState, useEffect } from 'react';
import { Socket } from 'socket.io-client';
import { useAgentStore } from '../../store/useAgentStore';
import { SessionSwitcher } from './SessionSwitcher';
import { TurnList } from './TurnList';
import { QuestionPrompt } from './QuestionPrompt';
import { Composer } from './Composer';
import { ArrowDown } from 'lucide-react';

interface AgentPanelProps {
  socket: Socket | null;
  onFileSelect?: (path: string) => void;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ socket }) => {
  const { turns, activeTurnId, pendingQuestion, setPendingQuestion } = useAgentStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  
  const activeTurn = turns.find(t => t.id === activeTurnId);
  const isStreaming = activeTurn ? !activeTurn.endedAt : false;
  
  // Auto-scroll logic
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      const el = scrollRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [turns, autoScroll]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    
    // If we are at the bottom (within a small threshold), re-enable autoscroll
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 10;
    
    if (isAtBottom && !autoScroll) {
      setAutoScroll(true);
    } else if (!isAtBottom && autoScroll) {
      setAutoScroll(false);
    }
  };

  const jumpToLatest = () => {
    setAutoScroll(true);
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  const handleSend = (prompt: string, model: string) => {
    if (!socket) return;
    socket.emit('agent.start', { prompt, model });
    jumpToLatest();
  };

  const handleAnswer = (answer: string) => {
    if (!socket || !pendingQuestion) return;
    socket.emit('agent.answer', {
      interaction_id: pendingQuestion.interactionId,
      answer,
    });
    // Clear immediately: the server has the answer, and leaving the prompt up
    // invites a second click that would be rejected as stale.
    setPendingQuestion(null);
  };

  const handleStop = () => {
    if (!socket || !activeTurnId) return;
    socket.emit('agent.stop', { turn_id: activeTurnId });
  };

  return (
    <div className="flex flex-col h-full bg-surface-1 overflow-hidden relative">
      {/* Header */}
      <div className="h-titlebar flex items-center justify-between px-3 border-b border-border-subtle shrink-0 bg-surface-1 z-10">
        <span className="text-xs font-medium text-text-tertiary uppercase tracking-wider">Agent</span>
        <SessionSwitcher />
      </div>

      {/* Scrollable Content */}
      <div 
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto custom-scrollbar relative"
        style={{ scrollBehavior: autoScroll ? 'auto' : 'smooth' }}
      >
        <TurnList turns={turns} />
        {pendingQuestion && (
          <QuestionPrompt question={pendingQuestion} onAnswer={handleAnswer} />
        )}
      </div>

      {/* Jump to latest pill */}
      {!autoScroll && (
        <div className="absolute bottom-[100px] left-0 right-0 flex justify-center z-20 pointer-events-none">
          <button 
            onClick={jumpToLatest}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-2 border border-border-default shadow-md text-xs text-text-primary hover:text-accent pointer-events-auto transition-colors"
          >
            <ArrowDown size={12} />
            Jump to latest
          </button>
        </div>
      )}

      {/* Composer Area */}
      <div className="p-3 bg-surface-1 border-t border-border-subtle shrink-0">
        <Composer 
          onSend={handleSend}
          onStop={handleStop}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
};
