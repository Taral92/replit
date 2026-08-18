import React from 'react';
import { HelpCircle } from 'lucide-react';
import { PendingQuestion } from '../../store/useAgentStore';
import { Button } from '../ui/Button';

interface QuestionPromptProps {
  question: PendingQuestion;
  onAnswer: (answer: string) => void;
}

/**
 * Rendered inline in the turn stream while the agent is parked waiting for an
 * answer. Deliberately not a modal: a modal covers the plan and the tool rows,
 * which is exactly the context needed to answer well.
 */
export const QuestionPrompt: React.FC<QuestionPromptProps> = ({ question, onAnswer }) => {
  return (
    <div className="my-2 rounded-md border border-accent-border bg-accent-muted p-3">
      <div className="mb-2 flex items-start gap-2">
        <HelpCircle size={14} strokeWidth={1.5} className="mt-0.5 shrink-0 text-accent" />
        <span className="text-base text-text-primary">{question.question}</span>
      </div>

      <div className="flex flex-wrap gap-2">
        {question.options.map((opt) => (
          <Button
            key={opt}
            variant="secondary"
            size="sm"
            className="h-7 text-xs"
            onClick={() => onAnswer(opt)}
          >
            {opt}
          </Button>
        ))}
      </div>

      <div className="mt-2 text-xs text-text-tertiary">
        The agent is waiting — nothing runs until you choose.
      </div>
    </div>
  );
};
