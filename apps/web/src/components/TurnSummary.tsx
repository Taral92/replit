import React, { useState, useEffect } from 'react';
import { 
  Loader2, 
  ChevronDown, 
  ChevronRight, 
  Folder, 
  FileCode, 
  Terminal, 
  CheckCircle2, 
  AlertCircle,
  ExternalLink,
  Code
} from 'lucide-react';
import { AgentTurn, TurnStep } from '../hooks/useAgentTurns';
import { tokens } from '../styles/tokens';

interface TurnSummaryProps {
  turn: AgentTurn;
  onFileSelect?: (file: string) => void;
}

export const TurnSummary: React.FC<TurnSummaryProps> = ({ turn, onFileSelect }) => {
  const isWorking = turn.isWorking || !turn.ended_at;
  const [isOpen, setIsOpen] = useState<boolean>(isWorking);
  const [elapsedSec, setElapsedSec] = useState<number>(0);

  // Auto-expand while working
  useEffect(() => {
    if (isWorking) {
      setIsOpen(true);
    }
  }, [isWorking]);

  // Live timer
  useEffect(() => {
    if (!turn.started_at) return;

    if (!isWorking && turn.ended_at) {
      const finalDuration = Math.max(1, Math.round((turn.ended_at - turn.started_at) / 1000));
      setElapsedSec(finalDuration);
      return;
    }

    const updateTimer = () => {
      const current = Date.now();
      const diff = Math.max(0, Math.round((current - turn.started_at) / 1000));
      setElapsedSec(diff);
    };

    updateTimer();
    const interval = setInterval(updateTimer, 500);

    return () => clearInterval(interval);
  }, [turn.started_at, turn.ended_at, isWorking]);

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const rem = seconds % 60;
    return `${mins}m ${rem}s`;
  };

  const steps = turn.steps || [];
  const exploredSteps = steps.filter(s => s.action === 'explored');
  const editedSteps = steps.filter(s => s.action === 'edited');
  const ranSteps = steps.filter(s => s.action === 'ran');
  const failedSteps = steps.filter(s => s.action === 'failed' || s.status === 'failed');

  const hasFailed = failedSteps.length > 0;
  const totalAdded = editedSteps.reduce((acc, s) => acc + (s.added || 0), 0);
  const totalRemoved = editedSteps.reduce((acc, s) => acc + (s.removed || 0), 0);

  const renderDiffLine = (line: string, index: number) => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return (
        <div key={index} style={{ backgroundColor: 'rgba(34, 197, 94, 0.12)', color: '#4ade80', padding: '1px 4px' }}>
          {line}
        </div>
      );
    }
    if (line.startsWith('-') && !line.startsWith('---')) {
      return (
        <div key={index} style={{ backgroundColor: 'rgba(239, 68, 68, 0.12)', color: '#f87171', padding: '1px 4px' }}>
          {line}
        </div>
      );
    }
    if (line.startsWith('@@')) {
      return (
        <div key={index} style={{ color: '#38bdf8', padding: '2px 4px', fontWeight: 600 }}>
          {line}
        </div>
      );
    }
    return (
      <div key={index} style={{ color: tokens.colors.textMuted, padding: '1px 4px' }}>
        {line}
      </div>
    );
  };

  return (
    <div 
      style={{
        backgroundColor: tokens.colors.surface2,
        border: `1px solid ${hasFailed ? 'rgba(239, 68, 68, 0.4)' : isWorking ? 'rgba(59, 130, 246, 0.4)' : tokens.colors.border}`,
        borderRadius: tokens.radii.lg,
        overflow: 'hidden',
        transition: `all ${tokens.transitions.morph}`,
        userSelect: 'none',
        boxShadow: isWorking ? '0 0 12px rgba(59, 130, 246, 0.08)' : 'none'
      }}
    >
      {/* 1. Interactive Header Bar */}
      <div 
        onClick={() => setIsOpen(!isOpen)}
        style={{
          padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          backgroundColor: hasFailed ? 'rgba(239, 68, 68, 0.08)' : isWorking ? tokens.colors.accentSubtle : tokens.colors.surface1,
          fontSize: tokens.typography.meta.fontSize,
          fontWeight: tokens.typography.meta.fontWeight,
          transition: `background-color ${tokens.transitions.fast}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm, flexWrap: 'wrap' }}>
          
          {/* Status Icon */}
          {isWorking ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: tokens.colors.accent }}>
              <Loader2 size={13} className="animate-spin" />
              <span>{turn.status || "Working..."} {elapsedSec}s</span>
            </div>
          ) : hasFailed ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: tokens.colors.error }}>
              <AlertCircle size={13} />
              <span>Action failed ({formatDuration(elapsedSec)})</span>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: tokens.colors.success }}>
              <CheckCircle2 size={13} />
              <span style={{ color: tokens.colors.textPrimary }}>Completed in {formatDuration(elapsedSec)}</span>
            </div>
          )}

          {/* Badges Summary */}
          {!isWorking && steps.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.xs, marginLeft: tokens.spacing.xs }}>
              {exploredSteps.length > 0 && (
                <span style={{ 
                  backgroundColor: 'rgba(255, 255, 255, 0.05)', 
                  padding: '1px 6px', 
                  borderRadius: '10px', 
                  color: tokens.colors.textMuted,
                  fontSize: '10px'
                }}>
                  {exploredSteps.length} explored
                </span>
              )}
              {editedSteps.length > 0 && (
                <span style={{ 
                  backgroundColor: 'rgba(59, 130, 246, 0.15)', 
                  padding: '1px 6px', 
                  borderRadius: '10px', 
                  color: tokens.colors.accent,
                  fontSize: '10px',
                  fontWeight: 500
                }}>
                  {editedSteps.length} edited (+{totalAdded} -{totalRemoved} lines)
                </span>
              )}
              {ranSteps.length > 0 && (
                <span style={{ 
                  backgroundColor: 'rgba(168, 85, 247, 0.15)', 
                  padding: '1px 6px', 
                  borderRadius: '10px', 
                  color: '#c084fc',
                  fontSize: '10px'
                }}>
                  {ranSteps.length} ran
                </span>
              )}
              {hasFailed && (
                <span style={{ 
                  backgroundColor: 'rgba(239, 68, 68, 0.15)', 
                  padding: '1px 6px', 
                  borderRadius: '10px', 
                  color: tokens.colors.error,
                  fontSize: '10px'
                }}>
                  {failedSteps.length} failed
                </span>
              )}
            </div>
          )}
        </div>

        {/* Expand / Collapse Icon */}
        <div style={{ color: tokens.colors.textDim, display: 'flex', alignItems: 'center', marginLeft: tokens.spacing.sm }}>
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </div>

      {/* 2. Collapsible Details Area */}
      {isOpen && (
        <div 
          style={{
            padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.sm,
            borderTop: `1px solid ${tokens.colors.border}`,
            backgroundColor: tokens.colors.surface0,
          }}
        >
          {steps.length === 0 ? (
            <div style={{ color: tokens.colors.textDim, fontSize: tokens.typography.meta.fontSize, padding: `${tokens.spacing.xs} 0` }}>
              {isWorking ? 'Inspecting files and preparing execution...' : 'No tool actions performed.'}
            </div>
          ) : (
            <>
              {/* Structured Failures Card */}
              {failedSteps.map((step) => (
                <div 
                  key={step.id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: tokens.spacing.xs,
                    backgroundColor: 'rgba(239, 68, 68, 0.06)',
                    padding: tokens.spacing.sm,
                    borderRadius: tokens.radii.sm,
                    border: '1px solid rgba(239, 68, 68, 0.25)'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm, color: tokens.colors.error, fontSize: tokens.typography.meta.fontSize, fontWeight: 500 }}>
                    <AlertCircle size={13} color={tokens.colors.error} />
                    <span>Failed: {step.tool} on {step.target}</span>
                  </div>

                  {step.error && (
                    <details style={{ fontSize: tokens.typography.meta.fontSize, color: tokens.colors.textDim, marginTop: '2px' }}>
                      <summary style={{ cursor: 'pointer', outline: 'none', color: tokens.colors.textMuted }}>View Error Trace</summary>
                      <pre style={{
                        backgroundColor: tokens.colors.surface1,
                        padding: tokens.spacing.sm,
                        borderRadius: tokens.radii.sm,
                        color: '#f87171',
                        overflowX: 'auto',
                        marginTop: tokens.spacing.xs,
                        fontFamily: tokens.typography.mono.fontFamily,
                        fontSize: tokens.typography.mono.fontSize,
                        border: '1px solid rgba(239, 68, 68, 0.2)'
                      }}>
                        {step.error}
                      </pre>
                    </details>
                  )}
                </div>
              ))}

              {/* Explored Files */}
              {exploredSteps.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ fontSize: '10px', fontWeight: 600, color: tokens.colors.textDim, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Explored Files ({exploredSteps.length})
                  </div>
                  {exploredSteps.map((step) => {
                    const countSuffix = step.count && step.count > 1 ? ` (x${step.count})` : '';
                    return (
                      <div 
                        key={step.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: tokens.spacing.sm,
                          color: tokens.colors.textMuted,
                          fontSize: tokens.typography.meta.fontSize,
                          padding: '2px 0'
                        }}
                      >
                        <Folder size={12} color="#dcb67a" />
                        <span style={{ color: tokens.colors.textPrimary }}>{step.target}</span>
                        {countSuffix && <span style={{ color: tokens.colors.textDim, fontSize: '10px' }}>{countSuffix}</span>}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Edited Files with Granular Line Changes & Syntax-Highlighted Diffs */}
              {editedSteps.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ fontSize: '10px', fontWeight: 600, color: tokens.colors.textDim, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Modified Files ({editedSteps.length})
                  </div>
                  {editedSteps.map((step) => {
                    const fileName = step.target.split('/').pop() || step.target;
                    const diffLines = step.diff ? step.diff.split('\n') : [];
                    
                    return (
                      <div key={step.id} style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xs }}>
                        <div 
                          onClick={() => onFileSelect && onFileSelect(step.target)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            cursor: 'pointer',
                            padding: `6px ${tokens.spacing.sm}`,
                            backgroundColor: tokens.colors.surface1,
                            borderRadius: tokens.radii.sm,
                            border: `1px solid ${tokens.colors.border}`,
                            transition: `all ${tokens.transitions.fast}`,
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.borderColor = tokens.colors.accent)}
                          onMouseLeave={(e) => (e.currentTarget.style.borderColor = tokens.colors.border)}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm, overflow: 'hidden' }}>
                            <FileCode size={13} color={tokens.colors.accent} />
                            <span style={{ color: tokens.colors.textPrimary, fontSize: tokens.typography.secondary.fontSize, fontWeight: 500 }}>
                              {fileName}
                            </span>
                            <span style={{ color: tokens.colors.textDim, fontSize: '10px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {step.target}
                            </span>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm, flexShrink: 0 }}>
                            <div style={{ display: 'flex', gap: tokens.spacing.xs, fontSize: tokens.typography.meta.fontSize, fontWeight: 600 }}>
                              <span style={{ color: tokens.colors.success, backgroundColor: 'rgba(34, 197, 94, 0.1)', padding: '1px 4px', borderRadius: '3px' }}>
                                +{step.added || 0}
                              </span>
                              <span style={{ color: tokens.colors.error, backgroundColor: 'rgba(239, 68, 68, 0.1)', padding: '1px 4px', borderRadius: '3px' }}>
                                -{step.removed || 0}
                              </span>
                            </div>
                            <ExternalLink size={11} color={tokens.colors.textDim} />
                          </div>
                        </div>

                        {/* Expandable Unified Diff Viewer with Line Highlighting */}
                        {step.diff && (
                          <details style={{ fontSize: tokens.typography.meta.fontSize, color: tokens.colors.textDim, paddingLeft: tokens.spacing.xs }}>
                            <summary style={{ cursor: 'pointer', outline: 'none', color: tokens.colors.textMuted, padding: '2px 0' }}>
                              View Unified Diff (+{step.added || 0} / -{step.removed || 0})
                            </summary>
                            <pre style={{
                              backgroundColor: tokens.colors.surface1,
                              padding: tokens.spacing.sm,
                              borderRadius: tokens.radii.sm,
                              overflowX: 'auto',
                              marginTop: tokens.spacing.xs,
                              fontFamily: tokens.typography.mono.fontFamily,
                              fontSize: tokens.typography.mono.fontSize,
                              lineHeight: 1.4,
                              border: `1px solid ${tokens.colors.border}`,
                              maxHeight: '220px'
                            }}>
                              {diffLines.map((l, i) => renderDiffLine(l, i))}
                            </pre>
                          </details>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Commands Ran */}
              {ranSteps.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ fontSize: '10px', fontWeight: 600, color: tokens.colors.textDim, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Executed Commands ({ranSteps.length})
                  </div>
                  {ranSteps.map((step) => (
                    <div 
                      key={step.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: tokens.spacing.sm,
                        color: tokens.colors.textMuted,
                        fontSize: tokens.typography.meta.fontSize,
                        padding: '2px 0'
                      }}
                    >
                      <Terminal size={12} color="#a855f7" />
                      <code style={{
                        backgroundColor: tokens.colors.surface1,
                        padding: `2px ${tokens.spacing.sm}`,
                        borderRadius: tokens.radii.sm,
                        color: tokens.colors.textPrimary,
                        fontFamily: tokens.typography.mono.fontFamily,
                        fontSize: tokens.typography.mono.fontSize,
                        border: `1px solid ${tokens.colors.border}`
                      }}>
                        {step.target}
                      </code>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};
