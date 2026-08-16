import React, { useState, useEffect } from 'react';
import { Socket } from 'socket.io-client';
import { Activity, Clock, FileCode, CheckCircle2, Terminal, Search, Edit3, Trash2 } from 'lucide-react';

interface ActivityEvent {
  time: string;
  action: string;
  type?: 'inspect' | 'patch' | 'verify' | 'command' | 'search' | 'generic';
}

interface AgentActivityProps {
  socket: Socket | null;
}

export const AgentActivity: React.FC<AgentActivityProps> = ({ socket }) => {
  const [activities, setActivities] = useState<ActivityEvent[]>([]);

  useEffect(() => {
    if (!socket) return;

    const handleActivity = (data: any) => {
      const now = new Date(data.timestamp || Date.now());
      const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
      
      const actionText = data.tool ? `${data.tool} ${data.target || ''}` : String(data.action || 'Unknown');
      const act = actionText.toLowerCase();
      let type: ActivityEvent['type'] = 'generic';
      if (act.includes('patch') || act.includes('writ') || data.action === 'edited') type = 'patch';
      else if (act.includes('inspect') || act.includes('read') || data.action === 'explored') type = 'inspect';
      else if (act.includes('verify') || act.includes('test') || act.includes('check')) type = 'verify';
      else if (act.includes('executing:') || act.includes('run_command') || data.action === 'ran') type = 'command';
      else if (act.includes('search') || act.includes('find')) type = 'search';

      setActivities(prev => [...prev, { time: timeStr, action: actionText, type }]);
    };

    socket.on('agent.step', handleActivity);

    return () => {
      socket.off('agent.step', handleActivity);
    };
  }, [socket]);

  const getActionColor = (type?: ActivityEvent['type']) => {
    switch (type) {
      case 'patch': return { bg: 'rgba(234, 179, 8, 0.1)', text: '#facc15', border: 'rgba(234, 179, 8, 0.3)', icon: Edit3 };
      case 'inspect': return { bg: 'rgba(59, 130, 246, 0.1)', text: '#60a5fa', border: 'rgba(59, 130, 246, 0.3)', icon: FileCode };
      case 'verify': return { bg: 'rgba(34, 197, 94, 0.1)', text: '#4ade80', border: 'rgba(34, 197, 94, 0.3)', icon: CheckCircle2 };
      case 'command': return { bg: 'rgba(168, 85, 247, 0.1)', text: '#c084fc', border: 'rgba(168, 85, 247, 0.3)', icon: Terminal };
      case 'search': return { bg: 'rgba(99, 102, 241, 0.1)', text: '#818cf8', border: 'rgba(99, 102, 241, 0.3)', icon: Search };
      default: return { bg: 'rgba(113, 113, 122, 0.1)', text: '#a1a1aa', border: 'rgba(113, 113, 122, 0.3)', icon: Activity };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: '#18181b', color: '#e4e4e7' }}>
      {/* Header */}
      <div style={{ 
        padding: '10px 16px', 
        fontSize: '11px', 
        fontWeight: '700', 
        color: '#a1a1aa', 
        textTransform: 'uppercase', 
        letterSpacing: '1px', 
        borderBottom: '1px solid #27272a',
        backgroundColor: 'rgba(24, 24, 27, 0.8)',
        backdropFilter: 'blur(10px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={13} color="#60a5fa" />
          <span>Agent Activity</span>
          {activities.length > 0 && (
            <span style={{ 
              backgroundColor: '#27272a', 
              color: '#93c5fd', 
              padding: '1px 6px', 
              borderRadius: '10px', 
              fontSize: '10px', 
              fontWeight: '600' 
            }}>
              {activities.length}
            </span>
          )}
        </div>

        {activities.length > 0 && (
          <button 
            onClick={() => setActivities([])}
            title="Clear Activity Log"
            style={{ 
              background: 'none', 
              border: 'none', 
              color: '#71717a', 
              cursor: 'pointer',
              padding: '2px 4px',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center'
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = '#ef4444'}
            onMouseLeave={(e) => e.currentTarget.style.color = '#71717a'}
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>
      
      {/* Timeline Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {activities.length === 0 ? (
          <div style={{ 
            color: '#52525b', 
            fontSize: '12px', 
            textAlign: 'center', 
            marginTop: '30px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '8px'
          }}>
            <Activity size={24} color="#3f3f46" />
            <span>Agent activity will appear here in real time.</span>
          </div>
        ) : (
          activities.map((act, i) => {
            const isLatest = i === activities.length - 1;
            const style = getActionColor(act.type);
            const Icon = style.icon;

            return (
              <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: '2px' }}>
                  <div style={{ 
                    width: '18px', 
                    height: '18px', 
                    borderRadius: '50%', 
                    backgroundColor: style.bg,
                    border: `1px solid ${style.border}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: isLatest ? '0 0 8px rgba(96, 165, 250, 0.4)' : 'none'
                  }}>
                    <Icon size={10} color={style.text} />
                  </div>
                  {i !== activities.length - 1 && (
                    <div style={{ width: '1px', height: '24px', backgroundColor: '#27272a', marginTop: '4px' }}></div>
                  )}
                </div>
                
                <div style={{ 
                  flex: 1, 
                  display: 'flex', 
                  flexDirection: 'column', 
                  gap: '3px',
                  backgroundColor: isLatest ? 'rgba(39, 39, 42, 0.5)' : 'transparent',
                  padding: isLatest ? '6px 8px' : '0',
                  borderRadius: '6px',
                  border: isLatest ? '1px solid #333338' : 'none'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#71717a', fontSize: '10px', fontWeight: '500' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={9} />
                      <span>{act.time}</span>
                    </div>
                    {isLatest && (
                      <span style={{ 
                        color: '#60a5fa', 
                        fontSize: '9px', 
                        fontWeight: '600',
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px'
                      }}>
                        Latest
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '12px', color: '#e4e4e7', lineHeight: '1.4', fontWeight: isLatest ? '500' : 'normal' }}>
                    {act.action}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
