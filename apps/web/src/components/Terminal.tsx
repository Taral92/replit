import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { Socket } from 'socket.io-client';
import { Terminal as TerminalIcon } from 'lucide-react';
import { tokens } from '../styles/tokens';
import { PanelEmptyState } from './PanelEmptyState';
import 'xterm/css/xterm.css';

interface TerminalProps {
  socket: Socket | null;
}

export const Terminal: React.FC<TerminalProps> = ({ socket }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);

  useEffect(() => {
    if (!terminalRef.current || !socket) return;

    // Initialize xterm.js with unified tokens
    const term = new XTerm({
      cursorBlink: true,
      convertEol: true,
      scrollback: 5000,
      theme: {
        background: tokens.colors.surface2,
        foreground: tokens.colors.textPrimary,
        cursor: tokens.colors.accent,
        selectionBackground: tokens.colors.borderStrong,
        black: tokens.colors.surface1,
        red: tokens.colors.error,
        green: tokens.colors.success,
        yellow: '#eab308',
        blue: tokens.colors.accent,
        magenta: '#a855f7',
        cyan: '#06b6d4',
        white: tokens.colors.textPrimary,
        brightBlack: tokens.colors.textDim,
      },
      fontSize: 12,
      fontFamily: tokens.typography.mono.fontFamily,
      lineHeight: 1.3,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);

    term.open(terminalRef.current);
    
    setTimeout(() => {
      try {
        fitAddon.fit();
      } catch (e) {
        // ignore
      }
    }, 50);
    
    xtermRef.current = term;

    term.onData((data) => {
      socket.emit('terminal.input', data);
    });

    const onTerminalData = (data: string) => {
      term.write(data);
    };
    socket.on('terminal.output', onTerminalData);

    const resizeObserver = new ResizeObserver(() => {
      try {
        fitAddon.fit();
        socket.emit('terminal.resize', {
          cols: term.cols,
          rows: term.rows,
        });
      } catch {
        // ignore
      }
    });

    if (terminalRef.current) {
      resizeObserver.observe(terminalRef.current);
    }

    return () => {
      socket.off('terminal.output', onTerminalData);
      resizeObserver.disconnect();
      term.dispose();
    };
  }, [socket]);

  if (!socket) {
    return <PanelEmptyState icon={TerminalIcon} label="Connecting to workspace..." loading={true} />;
  }

  return (
    <div 
      ref={terminalRef} 
      style={{ 
        width: '100%', 
        height: '100%', 
        backgroundColor: tokens.colors.surface2, 
        padding: '4px' 
      }} 
    />
  );
};
