import React from 'react';

export const DiffCard: React.FC<{ diff: string }> = ({ diff }) => {
  const lines = diff.split('\n').filter(Boolean);
  
  return (
    <div className="font-mono text-xs leading-relaxed bg-surface-1 border border-border-subtle rounded overflow-hidden">
      {lines.map((line, i) => {
        const isAdd = line.startsWith('+');
        const isDel = line.startsWith('-');
        const bgClass = isAdd ? 'bg-diff-add-bg' : isDel ? 'bg-diff-del-bg' : '';
        const textClass = isAdd ? 'text-diff-add-text' : isDel ? 'text-diff-del-text' : 'text-text-secondary';
        
        return (
          <div key={i} className={`flex px-2 py-0.5 ${bgClass}`}>
            <span className={`w-8 shrink-0 text-text-disabled select-none`}>{i + 1}</span>
            <span className={`flex-1 whitespace-pre-wrap ${textClass}`}>{line}</span>
          </div>
        );
      })}
    </div>
  );
};
