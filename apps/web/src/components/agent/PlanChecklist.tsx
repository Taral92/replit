import React from 'react';
import { Check, Circle } from 'lucide-react';

export interface PlanItem {
  id: string;
  text: string;
  status: 'pending' | 'in-progress' | 'completed';
}

export const PlanChecklist: React.FC<{ plan: PlanItem[] }> = ({ plan }) => {
  const completed = plan.filter(p => p.status === 'completed').length;
  
  return (
    <div className="my-3 px-3 py-2 bg-surface-1 border border-border-subtle rounded">
      <div className="flex justify-between items-center mb-2">
        <span className="text-sm font-medium text-text-primary">Plan</span>
        <span className="text-xs text-text-tertiary">{completed}/{plan.length}</span>
      </div>
      
      <div className="flex flex-col gap-1.5">
        {plan.map((item) => (
          <div key={item.id} className="flex items-start gap-2 text-sm">
            <div className="mt-0.5">
              {item.status === 'completed' && <Check size={14} className="text-success" />}
              {item.status === 'in-progress' && (
                <div className="relative flex items-center justify-center w-[14px] h-[14px]">
                  <Circle size={14} className="text-accent absolute" />
                  <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                </div>
              )}
              {item.status === 'pending' && <Circle size={14} className="text-text-disabled" />}
            </div>
            <span className={`${item.status === 'completed' ? 'text-text-tertiary' : item.status === 'in-progress' ? 'text-text-primary' : 'text-text-secondary'}`}>
              {item.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
