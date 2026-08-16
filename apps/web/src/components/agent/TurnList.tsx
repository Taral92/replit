import React from 'react';
import { AgentTurn } from '../../store/useAgentStore';
import { TurnItem } from './TurnItem';

export const TurnList: React.FC<{ turns: AgentTurn[] }> = ({ turns }) => {
  if (turns.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary p-4">
        <div className="text-center">
          <div className="text-base mb-2 font-medium text-text-secondary">Ready</div>
          <div className="text-sm">Type a prompt below to start a new turn.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col px-3 py-4">
      {turns.map(turn => (
        <TurnItem key={turn.id} turn={turn} />
      ))}
    </div>
  );
};
