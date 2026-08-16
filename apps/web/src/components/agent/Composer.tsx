import React, { useState, useRef, useEffect } from 'react';
import { Button } from '../ui/Button';
import { ArrowUp, Square, AtSign } from 'lucide-react';
import { IconButton } from '../ui/IconButton';

interface ComposerProps {
  onSend: (prompt: string, model: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  isBlocked?: boolean;
}

export const Composer: React.FC<ComposerProps> = ({ onSend, onStop, isStreaming, isBlocked }) => {
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('auto');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const newHeight = Math.min(Math.max(el.scrollHeight, 60), 240); // min ~3 rows, max ~12 rows
    el.style.height = `${newHeight}px`;
  }, [prompt]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (prompt.trim() && !isStreaming && !isBlocked) {
      onSend(prompt.trim(), model);
      setPrompt('');
    }
  };

  return (
    <div className={`p-2 bg-surface-2 rounded-lg border focus-within:border-accent-border transition-colors ${isBlocked ? 'opacity-50 pointer-events-none' : 'border-border-default'}`}>
      <textarea
        ref={textareaRef}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={isBlocked ? 'Approval required...' : 'Ask the agent... (Cmd+Enter to send)'}
        className="w-full bg-transparent resize-none outline-none text-base text-text-primary placeholder:text-text-disabled min-h-[60px] max-h-[240px] px-2 py-1"
        disabled={isBlocked}
      />
      
      <div className="flex items-center justify-between h-[28px] mt-1 px-1">
        <div className="flex items-center gap-1">
          {/* Ghost dropdown placeholder for model selector */}
          <select 
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="bg-transparent text-text-secondary hover:text-text-primary text-xs outline-none cursor-pointer appearance-none px-2 h-6"
          >
            <option value="auto">Auto</option>
            <option value="gpt-4">GPT-4</option>
            <option value="claude-3">Claude 3</option>
          </select>
          
          <IconButton tooltip="Mention file (@)" onClick={() => {}} className="w-6 h-6">
            <AtSign size={14} />
          </IconButton>
        </div>
        
        {isStreaming ? (
          <Button variant="danger" size="sm" onClick={onStop} className="h-6 w-6 p-0 rounded-full flex items-center justify-center">
            <Square size={12} fill="currentColor" />
          </Button>
        ) : (
          <Button variant="primary" size="sm" onClick={handleSend} disabled={!prompt.trim()} className="h-6 w-6 p-0 rounded-full flex items-center justify-center">
            <ArrowUp size={14} strokeWidth={2.5} />
          </Button>
        )}
      </div>
    </div>
  );
};
