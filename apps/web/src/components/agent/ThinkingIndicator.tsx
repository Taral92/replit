import React from 'react';

export const ThinkingIndicator: React.FC<{ status?: string }> = ({ status = 'Thinking' }) => {
  return (
    <div className="flex items-center gap-3 h-6 pl-[12px] border-l-2 border-border-subtle text-base text-text-tertiary">
      <div className="flex items-center gap-1.5 h-full">
        <div className="flex gap-0.5">
          <div className="w-1 h-1 rounded-full bg-accent animate-pulse" style={{ animationDelay: '0ms' }} />
          <div className="w-1 h-1 rounded-full bg-accent animate-pulse" style={{ animationDelay: '150ms' }} />
          <div className="w-1 h-1 rounded-full bg-accent animate-pulse" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
      <span className="font-medium">{status}</span>
    </div>
  );
};
