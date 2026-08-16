import React, { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { Sidebar } from './components/Sidebar';
import { Editor } from './components/Editor';
import { AgentPanel } from './components/agent/AgentPanel';
import { Preview } from './components/Preview';
import { Terminal } from './components/Terminal';
import { Panel, PanelGroup } from 'react-resizable-panels';
import { ResizeHandle } from './components/ResizeHandle';
import { Columns, Terminal as TerminalIcon, Code2, Globe } from 'lucide-react';
import { tokens } from './styles/tokens';
import { useSocketBridge } from './hooks/useSocketBridge';
import { useUiStore } from './store/useUiStore';

const App: React.FC = () => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [openFiles, setOpenFiles] = useState<string[]>([]);
  
  // Connect socket events to Zustand store
  useSocketBridge(socket);
  
  const { 
    showTerminal, showSidebar, showPreview, showAgentPanel,
    sidebarSize, terminalSize, agentPanelSize, previewSize,
    toggleTerminal, toggleSidebar, togglePreview,
    setSidebarSize, setTerminalSize, setAgentPanelSize, setPreviewSize
  } = useUiStore();

  useEffect(() => {
    const newSocket = io((import.meta as any).env.VITE_API_URL as string);

    newSocket.on('connect', () => setConnected(true));
    newSocket.on('disconnect', () => setConnected(false));

    setSocket(newSocket);

    return () => {
      newSocket.close();
    };
  }, []);

  const handleFileSelect = (path: string) => {
    setSelectedFile(path);
    setOpenFiles(prev => prev.includes(path) ? prev : [...prev, path]);
  };

  const handleTabClose = (path: string) => {
    setOpenFiles(prev => {
      const next = prev.filter(f => f !== path);
      if (selectedFile === path) {
        setSelectedFile(next.length > 0 ? next[next.length - 1] : null);
      }
      return next;
    });
  };

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100vh', 
      width: '100vw', 
      backgroundColor: tokens.colors.surface0, 
      color: tokens.colors.textPrimary, 
      overflow: 'hidden',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    }}>
      
      {/* Top Navigation Bar */}
      <div style={{ 
        height: '38px', 
        backgroundColor: tokens.colors.surface1, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        padding: `0 ${tokens.spacing.md}`, 
        borderBottom: `1px solid ${tokens.colors.border}`,
        userSelect: 'none',
        fontSize: tokens.typography.secondary.fontSize
      }}>
        {/* Brand & Project */}
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
          <Code2 size={16} color={tokens.colors.accent} />
          <span style={{ fontWeight: 700, color: '#ffffff', letterSpacing: '0.3px' }}>RunnerIDE</span>
          <span style={{ color: tokens.colors.textDim }}>/</span>
          <span style={{ color: tokens.colors.textMuted }}>workspace</span>
          {connected ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: tokens.colors.success, fontSize: '10px', marginLeft: '6px' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: tokens.colors.success }} />
              Live
            </span>
          ) : (
            <span style={{ color: tokens.colors.error, fontSize: '10px', marginLeft: '6px' }}>Connecting...</span>
          )}
        </div>

        {/* Top Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
          
          {/* Live Preview Toggle Pill */}
          <button
            onClick={togglePreview}
            title={showPreview ? "Hide Live Preview (Full Editor Focus)" : "Show Live Preview"}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: `3px ${tokens.spacing.sm}`,
              borderRadius: tokens.radii.sm,
              backgroundColor: showPreview ? tokens.colors.accentSubtle : tokens.colors.surface2,
              color: showPreview ? tokens.colors.accent : tokens.colors.textMuted,
              border: `1px solid ${showPreview ? tokens.colors.accent : tokens.colors.border}`,
              fontSize: tokens.typography.meta.fontSize,
              fontWeight: 500,
              cursor: 'pointer',
              transition: `all ${tokens.transitions.fast}`
            }}
          >
            <Globe size={12} />
            <span>{showPreview ? "Preview On" : "Preview"}</span>
          </button>

          {/* Toggle Explorer */}
          <button 
            onClick={toggleSidebar}
            title="Toggle Explorer"
            style={{ 
              background: 'none', 
              border: 'none', 
              color: showSidebar ? tokens.colors.textPrimary : tokens.colors.textDim, 
              cursor: 'pointer', 
              padding: '4px' 
            }}
          >
            <Columns size={15} />
          </button>
          
          {/* Toggle Terminal */}
          <button 
            onClick={toggleTerminal}
            title="Toggle Terminal"
            style={{ 
              background: 'none', 
              border: 'none', 
              color: showTerminal ? tokens.colors.textPrimary : tokens.colors.textDim, 
              cursor: 'pointer', 
              padding: '4px' 
            }}
          >
            <TerminalIcon size={15} />
          </button>
        </div>
      </div>

      {/* Main Resizable Layout */}
      <div style={{ flex: 1, display: 'flex', position: 'relative', overflow: 'hidden' }}>
        <PanelGroup direction="horizontal">
          
          {/* 1. Left Explorer Sidebar */}
          {showSidebar && (
            <>
              <Panel 
                defaultSize={sidebarSize} 
                onResize={setSidebarSize}
                minSize={12} 
                maxSize={30} 
                style={{ backgroundColor: tokens.colors.surface2, display: 'flex', flexDirection: 'column' }}
              >
                <Sidebar 
                  onFileSelect={handleFileSelect} 
                  selectedFile={selectedFile} 
                  socket={socket} 
                />
              </Panel>
              <ResizeHandle direction="horizontal" />
            </>
          )}

          {/* 2. Center: Editor + Optional Live Preview + Terminal */}
          <Panel defaultSize={54} minSize={30}>
            <PanelGroup direction="vertical">
              
              {/* Upper: Editor & Live Preview Split */}
              <Panel defaultSize={showTerminal ? 70 : 100} minSize={30}>
                <PanelGroup direction="horizontal">
                  
                  {/* Monaco Code Editor */}
                  <Panel 
                    defaultSize={showPreview ? 100 - previewSize : 100} 
                    minSize={25} 
                    style={{ display: 'flex', flexDirection: 'column' }}
                  >
                    <Editor 
                      selectedFile={selectedFile} 
                      openFiles={openFiles}
                      onTabSelect={handleFileSelect}
                      onTabClose={handleTabClose}
                      socket={socket} 
                    />
                  </Panel>
                  
                  {/* Live Preview Pane */}
                  {showPreview && (
                    <>
                      <ResizeHandle direction="horizontal" />
                      <Panel 
                        defaultSize={previewSize} 
                        onResize={setPreviewSize}
                        minSize={20} 
                        style={{ display: 'flex', flexDirection: 'column', borderLeft: `1px solid ${tokens.colors.border}` }}
                      >
                        <Preview socket={socket} onClose={togglePreview} />
                      </Panel>
                    </>
                  )}

                </PanelGroup>
              </Panel>

              {/* Lower: Bottom Terminal Pane */}
              {showTerminal && (
                <>
                  <ResizeHandle direction="vertical" />
                  <Panel 
                    defaultSize={terminalSize} 
                    onResize={setTerminalSize}
                    minSize={15} 
                    style={{ backgroundColor: tokens.colors.surface2, display: 'flex', flexDirection: 'column' }}
                  >
                    <div style={{ 
                      height: '28px', 
                      backgroundColor: tokens.colors.surface1, 
                      borderBottom: `1px solid ${tokens.colors.border}`,
                      display: 'flex',
                      alignItems: 'center',
                      padding: `0 ${tokens.spacing.md}`,
                      fontSize: tokens.typography.meta.fontSize,
                      fontWeight: tokens.typography.header.fontWeight,
                      color: tokens.colors.textMuted
                    }}>
                      <span>TERMINAL</span>
                    </div>
                    <div style={{ flex: 1, padding: '4px', overflow: 'hidden' }}>
                      <Terminal socket={socket} />
                    </div>
                  </Panel>
                </>
              )}

            </PanelGroup>
          </Panel>

          {/* 3. Right: Live AI Agent Chat */}
          <ResizeHandle direction="horizontal" />
          {showAgentPanel && (
            <Panel 
              defaultSize={agentPanelSize} 
              onResize={setAgentPanelSize}
              minSize={20} 
              style={{ display: 'flex', flexDirection: 'column', borderLeft: `1px solid ${tokens.colors.border}` }}
            >
              <AgentPanel 
                socket={socket} 
              />
            </Panel>
          )}

        </PanelGroup>
      </div>

    </div>
  );
};

export default App;
