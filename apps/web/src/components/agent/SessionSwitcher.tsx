import React from 'react';
import { useAgentStore } from '../../store/useAgentStore';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '../ui/DropdownMenu';
import { Button } from '../ui/Button';
import { ChevronDown } from 'lucide-react';

export const SessionSwitcher: React.FC = () => {
  const { sessions, activeSessionId, setActiveSession } = useAgentStore();
  
  const activeSession = sessions.find(s => s.id === activeSessionId);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="h-6 px-2 text-xs font-medium text-text-secondary hover:text-text-primary">
          {activeSession?.name || 'Session'}
          <ChevronDown size={14} className="ml-1 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {sessions.map(session => (
          <DropdownMenuItem 
            key={session.id} 
            onClick={() => setActiveSession(session.id)}
            className={session.id === activeSessionId ? 'bg-surface-3' : ''}
          >
            {session.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
