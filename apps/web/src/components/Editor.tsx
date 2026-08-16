import React, { useEffect, useState, useRef } from 'react';
import MonacoEditor from '@monaco-editor/react';
import { FileCode, Save, X, ChevronRight, Copy, Check } from 'lucide-react';
import { Socket } from 'socket.io-client';
import { getFileContent, saveFile } from '../lib/api';

interface EditorProps {
  selectedFile: string | null;
  openFiles?: string[];
  onTabSelect?: (file: string) => void;
  onTabClose?: (file: string) => void;
  socket: Socket | null;
}

export const Editor: React.FC<EditorProps> = ({ 
  selectedFile, 
  openFiles = [], 
  onTabSelect, 
  onTabClose, 
  socket 
}) => {
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [unsavedChanges, setUnsavedChanges] = useState(false);
  const [copiedPath, setCopiedPath] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!selectedFile) {
      setContent('');
      setUnsavedChanges(false);
      return;
    }

    setLoading(true);
    getFileContent(selectedFile)
      .then(text => {
        setContent(text);
        setUnsavedChanges(false);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load file content:", err);
        setContent('// Unable to load file content or file is empty.');
        setLoading(false);
      });
  }, [selectedFile]);

  // Live Auto-Save with 1.2s Debounce
  const triggerAutoSave = (newContent: string) => {
    if (!selectedFile) return;
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(async () => {
      try {
        setSaving(true);
        await saveFile(selectedFile, newContent);
        setUnsavedChanges(false);
        setSaving(false);
      } catch (err) {
        console.error("Auto-save failed:", err);
        setSaving(false);
      }
    }, 1200);
  };

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      setContent(value);
      setUnsavedChanges(true);
      triggerAutoSave(value);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    if (!isDragOver) setIsDragOver(true);
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDragOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const internalPath = e.dataTransfer.getData('application/x-ide-filepath') || e.dataTransfer.getData('text/plain');
    if (internalPath && onTabSelect) {
      onTabSelect(internalPath);
      return;
    }

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      for (let i = 0; i < e.dataTransfer.files.length; i++) {
        const file = e.dataTransfer.files[i];
        const text = await file.text();
        const path = file.name;
        await saveFile(path, text);
        if (onTabSelect) onTabSelect(path);
      }
    }
  };

  const handleBeforeMount = (monaco: any) => {
    monaco.languages.typescript.typescriptDefaults.setDiagnosticsOptions({
      noSemanticValidation: true,
      noSyntaxValidation: false,
    });
  };

  let language = 'typescript';
  if (selectedFile) {
    if (selectedFile.endsWith('.tsx') || selectedFile.endsWith('.ts')) language = 'typescript';
    else if (selectedFile.endsWith('.jsx') || selectedFile.endsWith('.js')) language = 'javascript';
    else if (selectedFile.endsWith('.py')) language = 'python';
    else if (selectedFile.endsWith('.html')) language = 'html';
    else if (selectedFile.endsWith('.css')) language = 'css';
    else if (selectedFile.endsWith('.json')) language = 'json';
    else if (selectedFile.endsWith('.md')) language = 'markdown';
  }

  const handleCopyPath = () => {
    if (selectedFile) {
      navigator.clipboard.writeText(selectedFile);
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 1500);
    }
  };

  const activeTabs = Array.from(new Set([...(openFiles.length > 0 ? openFiles : selectedFile ? [selectedFile] : [])]));

  return (
    <div 
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{ 
        flex: 1, 
        display: 'flex', 
        flexDirection: 'column', 
        height: '100%', 
        backgroundColor: '#18181b',
        position: 'relative'
      }}
    >
      {isDragOver && (
        <div style={{
          position: 'absolute',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(37, 99, 235, 0.12)',
          zIndex: 50,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#93c5fd',
          fontSize: '13px',
          fontWeight: '500',
          pointerEvents: 'none'
        }}>
          Drop file to open
        </div>
      )}

      {/* Clean Tab Bar */}
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        backgroundColor: '#141416',
        borderBottom: '1px solid #27272a',
        overflowX: 'auto'
      }}>
        <div 
          onWheel={(e) => {
            if (e.deltaY !== 0) e.currentTarget.scrollLeft += e.deltaY;
          }}
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            flex: 1, 
            overflowX: 'auto',
            scrollbarWidth: 'none'
          }}
        >
          {activeTabs.map((file) => {
            const isActive = file === selectedFile;
            const fileName = file.split('/').pop() || file;

            return (
              <div 
                key={file}
                onClick={() => onTabSelect && onTabSelect(file)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 12px',
                  fontSize: '12px',
                  fontWeight: isActive ? '600' : '400',
                  color: isActive ? '#ffffff' : '#858585',
                  backgroundColor: isActive ? '#18181b' : 'transparent',
                  borderRight: '1px solid #27272a',
                  borderTop: isActive ? '2px solid #3b82f6' : '2px solid transparent',
                  cursor: 'pointer',
                  userSelect: 'none',
                  whiteSpace: 'nowrap'
                }}
              >
                <FileCode size={13} color={isActive ? '#60a5fa' : '#71717a'} />
                <span>{fileName}</span>
                {isActive && unsavedChanges && (
                  <span style={{ color: '#facc15', fontSize: '14px', lineHeight: '8px' }}>•</span>
                )}
                {onTabClose && (
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      onTabClose(file);
                    }}
                    title="Close tab"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '1px',
                      borderRadius: '3px',
                      marginLeft: '3px',
                      color: '#71717a'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.color = '#ffffff'}
                    onMouseLeave={(e) => e.currentTarget.style.color = '#71717a'}
                  >
                    <X size={11} />
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Clean Breadcrumb path */}
        {selectedFile && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', paddingRight: '10px', fontSize: '11px', color: '#71717a' }}>
            <span>{selectedFile}</span>
            <button
              onClick={handleCopyPath}
              title="Copy Path"
              style={{ background: 'none', border: 'none', color: '#71717a', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
            >
              {copiedPath ? <Check size={11} color="#4ade80" /> : <Copy size={11} />}
            </button>
          </div>
        )}
      </div>

      {/* Editor Body */}
      <div style={{ flex: 1, position: 'relative' }}>
        {!selectedFile ? (
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            justifyContent: 'center', 
            alignItems: 'center', 
            height: '100%', 
            color: '#52525b', 
            fontSize: '12px',
            gap: '6px'
          }}>
            <FileCode size={30} color="#3f3f46" />
            <span>Select a file from the explorer to edit</span>
          </div>
        ) : loading ? (
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#71717a', fontSize: '12px' }}>
            Loading...
          </div>
        ) : (
          <MonacoEditor
            height="100%"
            language={language}
            theme="vs-dark"
            value={content}
            beforeMount={handleBeforeMount}
            onChange={handleEditorChange}
            options={{
              minimap: { enabled: true, scale: 0.75 },
              fontSize: 13,
              lineHeight: 20,
              wordWrap: 'on',
              padding: { top: 8, bottom: 8 },
              automaticLayout: true,
              cursorSmoothCaretAnimation: 'on',
              smoothScrolling: true,
              renderLineHighlight: 'all',
              tabSize: 2,
              scrollBeyondLastLine: true,
              mouseWheelScrollSensitivity: 1,
              fontFamily: "'JetBrains Mono', Menlo, Monaco, Consolas, monospace"
            }}
          />
        )}
      </div>
    </div>
  );
};
