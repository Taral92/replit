import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { Socket } from 'socket.io-client';
import 'xterm/css/xterm.css';

interface TerminalProps {
  socket: Socket;
}

export const Terminal: React.FC<TerminalProps> = ({ socket }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);

  useEffect(() => {
    if (!terminalRef.current) return;

    // Initialize xterm.js
    const term = new XTerm({
      cursorBlink: true,
      theme: {
        background: '#1e1e1e',
      },
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);

    term.open(terminalRef.current);
    fitAddon.fit();
    xtermRef.current = term;

    // Handle typing in the browser -> Send to backend
    term.onData((data) => {
      socket.emit('terminal:write', data);
    });

    // Handle receiving data from backend -> Write to browser
    const onTerminalData = (data: string) => {
      term.write(data);
    };
    socket.on('terminal:data', onTerminalData);

    // Handle resizing window -> Resize terminal
    const onResize = () => {
      fitAddon.fit();
      socket.emit('terminal:resize', {
        cols: term.cols,
        rows: term.rows,
      });
    };
    window.addEventListener('resize', onResize);

    // Initial resize event to sync sizes
    onResize();

    return () => {
      socket.off('terminal:data', onTerminalData);
      window.removeEventListener('resize', onResize);
      term.dispose();
    };
  }, [socket]);

  return <div ref={terminalRef} style={{ height: '100%', width: '100%' }} />;
};
