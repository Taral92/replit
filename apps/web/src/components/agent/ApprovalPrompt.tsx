import React from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from '../ui/Button';

interface ApprovalPromptProps {
  command: string;
  riskDescription: string;
  onApprove: () => void;
  onReject: () => void;
}

export const ApprovalPrompt: React.FC<ApprovalPromptProps> = ({ command, riskDescription, onApprove, onReject }) => {
  return (
    <div className="my-2 p-3 rounded-md bg-surface-2 border border-border-strong pl-[12px] ml-[12px]">
      <div className="flex items-start gap-2 mb-2">
        <AlertCircle size={16} className="text-warning shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="text-base font-medium text-text-primary mb-1">Human Approval Required</div>
          <div className="text-sm text-text-secondary">{riskDescription}</div>
        </div>
      </div>
      
      <div className="text-xs font-mono bg-surface-0 p-2 rounded text-text-primary mb-3 truncate border border-border-subtle">
        {command}
      </div>
      
      <div className="flex gap-2">
        <Button variant="primary" size="sm" className="h-7 text-xs flex-1" onClick={onApprove}>
          Approve
        </Button>
        <Button variant="ghost" size="sm" className="h-7 text-xs flex-1 text-text-secondary hover:text-text-primary" onClick={onReject}>
          Reject
        </Button>
      </div>
    </div>
  );
};
