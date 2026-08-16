import React from 'react';
import { GitBranch, RefreshCw, XCircle, AlertTriangle, Radio, Settings } from 'lucide-react';

interface StatusBarProps {
  cursorPos?: { line: number; col: number };
  language?: string;
  activePort?: string;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  cursorPos = { line: 1, col: 1 },
  language = 'TypeScript React',
  activePort = '3000',
}) => {
  return (
    <div
      style={{
        height: '24px',
        backgroundColor: '#18181b',
        borderTop: '1px solid #27272a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 8px',
        fontSize: '11px',
        color: '#a1a1aa',
        userSelect: 'none',
        zIndex: 20,
      }}
    >
      {/* Left items */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Branch */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            cursor: 'pointer',
            padding: '2px 4px',
            borderRadius: '3px',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#27272a')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
        >
          <GitBranch size={12} color="#60a5fa" />
          <span style={{ color: '#e4e4e7', fontWeight: '500' }}>main*</span>
          <RefreshCw size={10} color="#71717a" />
        </div>

        {/* Errors & Warnings */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: '#93c5fd' }}>
            <XCircle size={11} /> 0
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: '#facc15' }}>
            <AlertTriangle size={11} /> 0
          </span>
        </div>

        {/* Minikube / K8s context */}
        <span style={{ color: '#71717a', fontSize: '11px' }}>minikube</span>
        <span style={{ color: '#71717a', fontSize: '11px' }}>default</span>
      </div>

      {/* Right items */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <span>Ln {cursorPos.line}, Col {cursorPos.col}</span>
        <span>Spaces: 2</span>
        <span>UTF-8</span>
        <span>LF</span>
        
        {/* Language Badge */}
        <span style={{ color: '#93c5fd', fontWeight: '500' }}>
          {language}
        </span>

        {/* Go Live / Port */}
        <div
          title={`Dev server port ${activePort}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            backgroundColor: '#1e3a5f',
            color: '#60a5fa',
            padding: '1px 6px',
            borderRadius: '3px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '10px'
          }}
        >
          <Radio size={10} />
          <span>Port : {activePort}</span>
        </div>

        {/* Antigravity Settings */}
        <span style={{ color: '#71717a', display: 'flex', alignItems: 'center', gap: '3px' }}>
          <Settings size={11} /> Antigravity
        </span>
      </div>
    </div>
  );
};
