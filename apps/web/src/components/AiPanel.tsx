import React, { useState, useEffect, useRef } from 'react';
import { 
  Sparkles, 
  Plus, 
  ArrowUp, 
  History, 
  Trash2, 
  MessageSquare, 
  X, 
  Clock,
  Copy,
  Check,
  Zap,
  Play,
  Palette,
  Wrench
} from 'lucide-react';
import { Socket } from 'socket.io-client';
import { useAgentTurns, AgentTurn } from '../hooks/useAgentTurns';
import { TurnSummary } from './TurnSummary';
import { tokens } from '../styles/tokens';

interface ConversationTurn {
  id: string;
  userPrompt: string;
  assistantResponse?: string;
  timestamp: number;
}

interface ChatSession {
  id: string;
  title: string;
  updatedAt: number;
  turns: ConversationTurn[];
  persistedTurnData?: Record<string, AgentTurn>;
}

interface AiPanelProps {
  socket: Socket | null;
  onFileSelect?: (file: string) => void;
}

const STORAGE_KEY = 'runneride_chat_sessions_v4';
const ACTIVE_SESSION_KEY = 'runneride_active_session_id_v4';

const STARTER_PROMPTS = [
  { icon: Palette, text: 'Build a modern hero section with Aceternity 3D cards', label: 'UI Design' },
  { icon: Play, text: 'Start Next.js dev server and verify preview on 3001', label: 'Dev Server' },
  { icon: Zap, text: 'Add dark mode toggle with Tailwind CSS', label: 'Feature' },
  { icon: Wrench, text: 'Inspect workspace files and fix any build warnings', label: 'Diagnostics' },
];

const getInitialSessions = (): { sessions: ChatSession[]; activeId: string } => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed: ChatSession[] = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        const savedActiveId = localStorage.getItem(ACTIVE_SESSION_KEY) || parsed[0].id;
        const exists = parsed.some(s => s.id === savedActiveId);
        return { 
          sessions: parsed, 
          activeId: exists ? savedActiveId : parsed[0].id 
        };
      }
    }
  } catch (e) {
    console.error("Failed to load chat history:", e);
  }

  const defaultSession: ChatSession = {
    id: `session_${Date.now()}`,
    title: 'Workspace Task',
    updatedAt: Date.now(),
    turns: []
  };

  return { sessions: [defaultSession], activeId: defaultSession.id };
};

const generateContextTitle = (firstPrompt: string, defaultFallback = 'Workspace Task'): string => {
  if (!firstPrompt) return defaultFallback;

  const raw = firstPrompt.trim();
  const fileMatch = raw.match(/\b([a-zA-Z0-9_\-\/]+\.(?:tsx|ts|jsx|js|py|css|html|json|md))\b/i);
  const mentionedFile = fileMatch ? fileMatch[1].split('/').pop() : null;

  let cleaned = raw
    .replace(/^(can you|please|i want to|i need to|help me|could you|make it so|build a|create a|implement|add|fix|update|how to)/i, '')
    .trim();
  if (!cleaned) cleaned = raw;

  cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  if (cleaned.length > 36) {
    cleaned = cleaned.slice(0, 34).trim() + '...';
  }

  if (mentionedFile && !cleaned.toLowerCase().includes(mentionedFile.toLowerCase())) {
    return `${mentionedFile} › ${cleaned}`;
  }

  return cleaned;
};

// Rich Markdown & Code Formatter
const FormattedMessage: React.FC<{ content: string }> = ({ content }) => {
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  // Split code blocks
  const parts = content.split(/(```[\s\S]*?```)/g);

  const copyCode = (code: string, idx: number) => {
    navigator.clipboard.writeText(code);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 1500);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: tokens.typography.body.fontSize, lineHeight: tokens.typography.body.lineHeight, color: tokens.colors.textPrimary }}>
      {parts.map((part, index) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const lines = part.slice(3, -3).trim().split('\n');
          const lang = lines[0].includes(' ') ? '' : lines[0];
          const code = lang ? lines.slice(1).join('\n') : lines.join('\n');

          return (
            <div 
              key={index} 
              style={{ 
                backgroundColor: '#141416', 
                borderRadius: tokens.radii.md, 
                border: `1px solid ${tokens.colors.borderSubtle}`, 
                overflow: 'hidden', 
                margin: '4px 0' 
              }}
            >
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between', 
                padding: '4px 10px', 
                backgroundColor: tokens.colors.surfaceElevated, 
                borderBottom: `1px solid ${tokens.colors.borderSubtle}`, 
                fontSize: '11px', 
                color: tokens.colors.textMuted 
              }}>
                <span>{lang || 'code'}</span>
                <button
                  onClick={() => copyCode(code, index)}
                  style={{ 
                    background: 'none', 
                    border: 'none', 
                    color: tokens.colors.textMuted, 
                    cursor: 'pointer', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '4px', 
                    fontSize: '10px' 
                  }}
                >
                  {copiedIdx === index ? <Check size={11} color="#4ade80" /> : <Copy size={11} />}
                  <span>{copiedIdx === index ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <pre style={{ 
                padding: '10px', 
                margin: 0, 
                fontFamily: tokens.typography.mono.fontFamily, 
                fontSize: tokens.typography.mono.fontSize, 
                overflowX: 'auto', 
                color: '#f4f4f5' 
              }}>
                {code}
              </pre>
            </div>
          );
        }

        // Standard text lines
        return (
          <div key={index} style={{ whiteSpace: 'pre-wrap' }}>
            {part}
          </div>
        );
      })}
    </div>
  );
};

export const AiPanel: React.FC<AiPanelProps> = ({ socket, onFileSelect }) => {
  const initialData = useRef(getInitialSessions());
  const [sessions, setSessions] = useState<ChatSession[]>(initialData.current.sessions);
  const [activeSessionId, setActiveSessionId] = useState<string>(initialData.current.activeId);
  const [showHistory, setShowHistory] = useState(false);

  const { turns: liveTurns, clearTurns } = useAgentTurns(socket);

  const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
  const [conversationTurns, setConversationTurns] = useState<ConversationTurn[]>(activeSession ? activeSession.turns : []);
  const [persistedTurns, setPersistedTurns] = useState<Record<string, AgentTurn>>(activeSession?.persistedTurnData || {});

  const [input, setInput] = useState('');
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [loading, setLoading] = useState(false);
  const activeTurnIdRef = useRef<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const target = sessions.find(s => s.id === activeSessionId);
    if (target) {
      setConversationTurns(target.turns || []);
      setPersistedTurns(target.persistedTurnData || {});
      localStorage.setItem(ACTIVE_SESSION_KEY, target.id);
    }
  }, [activeSessionId]);

  useEffect(() => {
    if (!activeSessionId) return;

    setSessions(prev => {
      const updated = prev.map(s => {
        if (s.id === activeSessionId) {
          let title = s.title;
          const firstPrompt = conversationTurns[0]?.userPrompt;
          if (firstPrompt && (s.title === 'Workspace Task' || s.title === 'New Conversation' || !s.title)) {
            title = generateContextTitle(firstPrompt);
          }

          const mergedTurnData = { ...s.persistedTurnData, ...persistedTurns, ...liveTurns };

          return {
            ...s,
            title,
            updatedAt: Date.now(),
            turns: conversationTurns,
            persistedTurnData: mergedTurnData
          };
        }
        return s;
      });

      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (e) {
        console.error("Failed to save chat sessions:", e);
      }
      return updated;
    });
  }, [conversationTurns, liveTurns, persistedTurns, activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversationTurns, liveTurns, loading]);

  useEffect(() => {
    if (!socket) return;

    const handleTurnStart = (data: { turn_id: string; started_at: number; prompt?: string }) => {
      activeTurnIdRef.current = data.turn_id;
      setLoading(true);
    };

    const handleMessage = (data: any) => {
      const turnId = typeof data === 'object' && data.turn_id ? data.turn_id : activeTurnIdRef.current;
      const content = typeof data === 'object' && data.content !== undefined ? data.content : String(data);

      if (turnId) {
        setConversationTurns(prev => prev.map(t => {
          if (t.id === turnId) {
            return { ...t, assistantResponse: content };
          }
          return t;
        }));
      }
      setLoading(false);
    };

    const handleTurnEnd = () => {
      setLoading(false);
      activeTurnIdRef.current = null;
    };

    socket.on('agent.turn.started', handleTurnStart);
    socket.on('agent.message', handleMessage);
    socket.on('agent.turn.completed', handleTurnEnd);

    return () => {
      socket.off('agent.turn.started', handleTurnStart);
      socket.off('agent.message', handleMessage);
      socket.off('agent.turn.completed', handleTurnEnd);
    };
  }, [socket]);

  const handleSendPrompt = (promptText: string) => {
    if (!promptText.trim() || !socket || loading) return;

    const query = promptText.trim();
    const turnId = `turn_${Date.now()}`;
    activeTurnIdRef.current = turnId;

    const newTurn: ConversationTurn = {
      id: turnId,
      userPrompt: query,
      timestamp: Date.now()
    };

    setConversationTurns(prev => [...prev, newTurn]);
    setLoading(true);

    socket.emit('agent.start', {
      prompt: query,
      model: selectedModel,
      turn_id: turnId
    });

    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleNewChat = () => {
    clearTurns();
    const newSession: ChatSession = {
      id: `session_${Date.now()}`,
      title: 'Workspace Task',
      updatedAt: Date.now(),
      turns: []
    };

    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
    setConversationTurns([]);
    setPersistedTurns({});
    setShowHistory(false);
  };

  const handleDeleteSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setSessions(prev => {
      const filtered = prev.filter(s => s.id !== sessionId);
      if (filtered.length === 0) {
        const fresh: ChatSession = {
          id: `session_${Date.now()}`,
          title: 'Workspace Task',
          updatedAt: Date.now(),
          turns: []
        };
        setActiveSessionId(fresh.id);
        setConversationTurns([]);
        setPersistedTurns({});
        return [fresh];
      }
      if (activeSessionId === sessionId) {
        setActiveSessionId(filtered[0].id);
        setConversationTurns(filtered[0].turns || []);
        setPersistedTurns(filtered[0].persistedTurnData || {});
      }
      return filtered;
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendPrompt(input);
    }
  };

  const formatTimeAgo = (timestamp: number) => {
    const diff = Math.floor((Date.now() - timestamp) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  const allTurnsMap = { ...persistedTurns, ...liveTurns };

  return (
    <div 
      style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        height: '100%', 
        backgroundColor: tokens.colors.bg, 
        color: tokens.colors.textPrimary,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        position: 'relative',
      }}
    >
      
      {/* 1. Header */}
      <div 
        style={{ 
          height: '38px',
          padding: `0 ${tokens.spacing.md}`, 
          backgroundColor: tokens.colors.surfaceSubtle, 
          borderBottom: `1px solid ${tokens.colors.borderSubtle}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          userSelect: 'none'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
          <Sparkles size={14} color={tokens.colors.accent} />
          <span style={{ 
            fontSize: tokens.typography.header.fontSize, 
            fontWeight: tokens.typography.header.fontWeight, 
            color: tokens.colors.textPrimary, 
            letterSpacing: '0.2px'
          }}>
            AI Engineer
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.xs }}>
          <button 
            onClick={() => setShowHistory(!showHistory)}
            title="Chat History"
            style={{ 
              background: showHistory ? tokens.colors.surface : 'transparent', 
              border: `1px solid ${showHistory ? tokens.colors.border : tokens.colors.borderSubtle}`, 
              color: showHistory ? tokens.colors.accent : tokens.colors.textMuted, 
              cursor: 'pointer', 
              padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`, 
              borderRadius: tokens.radii.sm,
              fontSize: tokens.typography.meta.fontSize,
              fontWeight: tokens.typography.meta.fontWeight,
              display: 'flex',
              alignItems: 'center',
              gap: tokens.spacing.xs,
              transition: `background-color ${tokens.transitions.fast}, color ${tokens.transitions.fast}`,
            }}
          >
            <History size={12} />
            <span>History</span>
          </button>

          <button 
            onClick={handleNewChat}
            title="New Chat"
            style={{ 
              background: tokens.colors.accent, 
              border: 'none', 
              color: '#ffffff', 
              cursor: 'pointer', 
              padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`, 
              borderRadius: tokens.radii.sm,
              fontSize: tokens.typography.meta.fontSize,
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
              transition: `opacity ${tokens.transitions.fast}`,
            }}
            onMouseEnter={(e) => e.currentTarget.style.opacity = '0.9'}
            onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
          >
            <Plus size={12} />
            <span>New</span>
          </button>
        </div>
      </div>

      {/* 2. History Drawer */}
      {showHistory && (
        <div 
          style={{
            position: 'absolute',
            top: '39px',
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: tokens.colors.bg,
            zIndex: 40,
            display: 'flex',
            flexDirection: 'column',
            borderBottom: `1px solid ${tokens.colors.borderSubtle}`,
          }}
        >
          <div 
            style={{ 
              padding: `${tokens.spacing.sm} ${tokens.spacing.md}`, 
              borderBottom: `1px solid ${tokens.colors.borderSubtle}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: tokens.typography.meta.fontSize,
              fontWeight: tokens.typography.meta.fontWeight,
              color: tokens.colors.textMuted,
            }}
          >
            <span>PAST SESSIONS ({sessions.length})</span>
            <button 
              onClick={() => setShowHistory(false)}
              style={{ background: 'none', border: 'none', color: tokens.colors.textDim, cursor: 'pointer', padding: tokens.spacing.xs }}
            >
              <X size={14} />
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: tokens.spacing.sm }}>
            {sessions.map((sess) => {
              const isActive = sess.id === activeSessionId;
              const turnCount = sess.turns ? sess.turns.length : 0;

              return (
                <div
                  key={sess.id}
                  onClick={() => {
                    setActiveSessionId(sess.id);
                    setShowHistory(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                    borderRadius: tokens.radii.md,
                    backgroundColor: isActive ? tokens.colors.surface : 'transparent',
                    border: `1px solid ${isActive ? tokens.colors.accent : 'transparent'}`,
                    cursor: 'pointer',
                    marginBottom: tokens.spacing.xs,
                    transition: `background-color ${tokens.transitions.fast}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm, overflow: 'hidden' }}>
                    <MessageSquare size={13} color={isActive ? tokens.colors.accent : tokens.colors.textDim} />
                    <div style={{ overflow: 'hidden' }}>
                      <div style={{ 
                        fontSize: tokens.typography.secondary.fontSize, 
                        fontWeight: isActive ? 500 : 400, 
                        color: isActive ? tokens.colors.textPrimary : tokens.colors.textMuted, 
                        overflow: 'hidden', 
                        textOverflow: 'ellipsis', 
                        whiteSpace: 'nowrap' 
                      }}>
                        {sess.title}
                      </div>
                      <div style={{ 
                        fontSize: tokens.typography.meta.fontSize, 
                        color: tokens.colors.textDim, 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: tokens.spacing.xs, 
                        marginTop: '2px' 
                      }}>
                        <span><Clock size={9} style={{ display: 'inline', marginRight: '2px' }} />{formatTimeAgo(sess.updatedAt)}</span>
                        <span>•</span>
                        <span>{turnCount} {turnCount === 1 ? 'task' : 'tasks'}</span>
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={(e) => handleDeleteSession(e, sess.id)}
                    title="Delete Session"
                    style={{
                      background: 'none',
                      border: 'none',
                      color: tokens.colors.textDim,
                      cursor: 'pointer',
                      padding: tokens.spacing.xs,
                      borderRadius: tokens.radii.sm,
                      opacity: 0.7,
                      transition: `color ${tokens.transitions.fast}, opacity ${tokens.transitions.fast}`,
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = tokens.colors.error; e.currentTarget.style.opacity = '1'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = tokens.colors.textDim; e.currentTarget.style.opacity = '0.7'; }}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. Conversation Message Stream */}
      <div 
        style={{ 
          flex: 1, 
          overflowY: 'auto', 
          padding: tokens.spacing.md, 
          display: 'flex', 
          flexDirection: 'column', 
          gap: tokens.spacing.lg,
        }}
      >
        {/* Starter Hero with Quick Prompts */}
        {conversationTurns.length === 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', padding: '12px 4px' }}>
            <div>
              <h3 style={{ margin: '0 0 4px 0', fontSize: '14px', fontWeight: 600, color: tokens.colors.textPrimary }}>
                How can I help you build today?
              </h3>
              <p style={{ margin: 0, fontSize: tokens.typography.secondary.fontSize, color: tokens.colors.textMuted }}>
                I can edit code, generate Next.js components, run terminal commands, and verify your preview live.
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '6px', marginTop: '4px' }}>
              {STARTER_PROMPTS.map((prompt, pIdx) => {
                const IconComponent = prompt.icon;
                return (
                  <button
                    key={pIdx}
                    onClick={() => handleSendPrompt(prompt.text)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '8px 10px',
                      backgroundColor: tokens.colors.surfaceElevated,
                      border: `1px solid ${tokens.colors.borderSubtle}`,
                      borderRadius: tokens.radii.md,
                      color: tokens.colors.textPrimary,
                      fontSize: '12px',
                      textAlign: 'left',
                      cursor: 'pointer',
                      transition: `all ${tokens.transitions.fast}`
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = tokens.colors.accent;
                      e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.08)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = tokens.colors.borderSubtle;
                      e.currentTarget.style.backgroundColor = tokens.colors.surfaceElevated;
                    }}
                  >
                    <IconComponent size={13} color={tokens.colors.accent} style={{ flexShrink: 0 }} />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {prompt.text}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {conversationTurns.map((turnItem, idx) => {
          const isLatestTurn = idx === conversationTurns.length - 1;
          const isActuallyWorking = isLatestTurn && loading && !turnItem.assistantResponse;

          const liveData = allTurnsMap[turnItem.id];
          const matchedTurnData: AgentTurn = {
            turn_id: turnItem.id,
            started_at: liveData?.started_at || turnItem.timestamp,
            ended_at: isActuallyWorking ? null : (liveData?.ended_at || turnItem.timestamp + 3000),
            isWorking: isActuallyWorking,
            steps: liveData?.steps || []
          };

          return (
            <div 
              key={turnItem.id} 
              style={{ 
                display: 'flex', 
                flexDirection: 'column', 
                gap: tokens.spacing.sm,
                animation: 'fadeSlideUp 150ms ease-out',
              }}
            >
              {/* User Prompt Bubble */}
              <div 
                style={{
                  backgroundColor: tokens.colors.surface,
                  color: tokens.colors.textPrimary,
                  padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                  borderRadius: tokens.radii.lg,
                  fontSize: tokens.typography.body.fontSize,
                  lineHeight: tokens.typography.body.lineHeight,
                  alignSelf: 'stretch',
                  border: `1px solid ${tokens.colors.borderSubtle}`,
                }}
              >
                {turnItem.userPrompt}
              </div>

              {/* Turn Execution Card */}
              <TurnSummary 
                turn={matchedTurnData} 
                onFileSelect={onFileSelect} 
              />

              {/* Markdown-Formatted Assistant Response */}
              {turnItem.assistantResponse && (
                <div style={{ padding: `0 ${tokens.spacing.xs}` }}>
                  <FormattedMessage content={turnItem.assistantResponse} />
                </div>
              )}
            </div>
          );
        })}

        <div ref={messagesEndRef} />
      </div>

      {/* 4. Bottom Input Area */}
      <div 
        style={{ 
          padding: `${tokens.spacing.sm} ${tokens.spacing.md}`, 
          backgroundColor: tokens.colors.surfaceSubtle, 
          borderTop: `1px solid ${tokens.colors.borderSubtle}`,
        }}
      >
        <div 
          style={{
            backgroundColor: tokens.colors.surfaceElevated,
            border: `1px solid ${tokens.colors.border}`,
            borderRadius: tokens.radii.lg,
            padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.sm,
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask AI to edit files, build components, or run commands..."
            rows={2}
            style={{
              width: '100%',
              background: 'none',
              border: 'none',
              color: tokens.colors.textPrimary,
              fontSize: tokens.typography.secondary.fontSize,
              lineHeight: tokens.typography.secondary.lineHeight,
              resize: 'none',
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={{
                backgroundColor: tokens.colors.surface,
                color: tokens.colors.textMuted,
                border: `1px solid ${tokens.colors.borderSubtle}`,
                borderRadius: tokens.radii.sm,
                padding: `2px ${tokens.spacing.xs}`,
                fontSize: tokens.typography.meta.fontSize,
                fontWeight: tokens.typography.meta.fontWeight,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="auto">Auto Router (Fastest)</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="claude">Claude 3.5 Sonnet</option>
            </select>

            <button
              onClick={() => handleSendPrompt(input)}
              disabled={!input.trim() || loading}
              style={{
                backgroundColor: input.trim() && !loading ? tokens.colors.accent : tokens.colors.surface,
                color: input.trim() && !loading ? '#ffffff' : tokens.colors.textDim,
                border: 'none',
                borderRadius: tokens.radii.sm,
                padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`,
                cursor: input.trim() && !loading ? 'pointer' : 'default',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: `background-color ${tokens.transitions.fast}`,
              }}
            >
              <ArrowUp size={13} />
            </button>
          </div>
        </div>
      </div>

    </div>
  );
};
