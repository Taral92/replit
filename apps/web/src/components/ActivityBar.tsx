import React from 'react';
import { Files, Search, GitBranch, Puzzle, Bot, Settings } from 'lucide-react';

interface ActivityBarProps {
  activeTab: 'explorer' | 'search' | 'git' | 'extensions' | 'ai';
  onTabChange: (tab: 'explorer' | 'search' | 'git' | 'extensions' | 'ai') => void;
  onSettingsClick?: () => void;
}

export const ActivityBar: React.FC<ActivityBarProps> = ({
  activeTab,
  onTabChange,
  onSettingsClick,
}) => {
  return (
    <div
      style={{
        width: '48px',
        backgroundColor: '#18181b',
        borderRight: '1px solid #27272a',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 0',
        userSelect: 'none',
        zIndex: 20,
      }}
    >
      {/* Top Icons */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', width: '100%' }}>
        
        {/* Explorer */}
        <button
          onClick={() => onTabChange('explorer')}
          title="Explorer (Cmd+Shift+E)"
          style={{
            background: 'none',
            border: 'none',
            width: '100%',
            height: '40px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            position: 'relative',
            color: activeTab === 'explorer' ? '#ffffff' : '#71717a',
          }}
        >
          {activeTab === 'explorer' && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: '6px',
                bottom: '6px',
                width: '2px',
                backgroundColor: '#ffffff',
              }}
            />
          )}
          <Files size={20} />
        </button>

        {/* Search */}
        <button
          onClick={() => onTabChange('search')}
          title="Search (Cmd+Shift+F)"
          style={{
            background: 'none',
            border: 'none',
            width: '100%',
            height: '40px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            position: 'relative',
            color: activeTab === 'search' ? '#ffffff' : '#71717a',
          }}
        >
          {activeTab === 'search' && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: '6px',
                bottom: '6px',
                width: '2px',
                backgroundColor: '#ffffff',
              }}
            />
          )}
          <Search size={20} />
        </button>

        {/* Source Control / Git */}
        <button
          onClick={() => onTabChange('git')}
          title="Source Control (Cmd+Shift+G)"
          style={{
            background: 'none',
            border: 'none',
            width: '100%',
            height: '40px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            position: 'relative',
            color: activeTab === 'git' ? '#ffffff' : '#71717a',
          }}
        >
          {activeTab === 'git' && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: '6px',
                bottom: '6px',
                width: '2px',
                backgroundColor: '#ffffff',
              }}
            />
          )}
          <GitBranch size={20} />
          {/* Antigravity-style badge */}
          <span
            style={{
              position: 'absolute',
              top: '6px',
              right: '6px',
              backgroundColor: '#2563eb',
              color: '#ffffff',
              fontSize: '9px',
              fontWeight: '700',
              padding: '1px 4px',
              borderRadius: '8px',
              lineHeight: '11px',
            }}
          >
            98
          </span>
        </button>

        {/* Extensions */}
        <button
          onClick={() => onTabChange('extensions')}
          title="Extensions (Cmd+Shift+X)"
          style={{
            background: 'none',
            border: 'none',
            width: '100%',
            height: '40px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            position: 'relative',
            color: activeTab === 'extensions' ? '#ffffff' : '#71717a',
          }}
        >
          {activeTab === 'extensions' && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: '6px',
                bottom: '6px',
                width: '2px',
                backgroundColor: '#ffffff',
              }}
            />
          )}
          <Puzzle size={20} />
        </button>

        {/* AI Agent */}
        <button
          onClick={() => onTabChange('ai')}
          title="AI Engineer Panel"
          style={{
            background: 'none',
            border: 'none',
            width: '100%',
            height: '40px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            position: 'relative',
            color: activeTab === 'ai' ? '#38bdf8' : '#71717a',
          }}
        >
          {activeTab === 'ai' && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: '6px',
                bottom: '6px',
                width: '2px',
                backgroundColor: '#38bdf8',
              }}
            />
          )}
          <Bot size={20} />
        </button>
      </div>

      {/* Bottom Icons (Settings & Avatar) */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', width: '100%' }}>
        <button
          onClick={onSettingsClick}
          title="Settings (Cmd+,)"
          style={{
            background: 'none',
            border: 'none',
            width: '100%',
            height: '36px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: '#71717a',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#ffffff')}
          onMouseLeave={(e) => (e.currentTarget.style.color = '#71717a')}
        >
          <Settings size={19} />
        </button>

        {/* Profile Pink Avatar Circle */}
        <div
          title="Account: Taral Patel"
          style={{
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            backgroundColor: '#ec4899',
            color: '#ffffff',
            fontSize: '11px',
            fontWeight: '700',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 0 6px rgba(236, 72, 153, 0.4)',
          }}
        >
          T
        </div>
      </div>
    </div>
  );
};
