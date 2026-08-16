import React, { useEffect, useState, useRef } from 'react';
import { 
  Folder, 
  ChevronRight, 
  ChevronDown, 
  FilePlus, 
  FolderPlus, 
  RefreshCw, 
  Trash2, 
  AlertOctagon, 
  RotateCcw,
  FileCode
} from 'lucide-react';
import { Socket } from 'socket.io-client';
import { tokens } from '../styles/tokens';
import { PanelEmptyState } from './PanelEmptyState';
import { listFiles, createFile, createFolder, saveFile, getFileContent, deleteFile, resetWorkspace } from '../lib/api';

interface FileNode {
  name: string;
  type: 'file' | 'directory';
  path: string;
  children?: FileNode[];
}

interface DeletedItem {
  path: string;
  name: string;
  content: string;
  isDirectory: boolean;
  timestamp: number;
}

interface SidebarProps {
  onFileSelect: (path: string) => void;
  selectedFile: string | null;
  socket: Socket | null;
}

const removeNodeFromTree = (nodes: FileNode[], targetPath: string): FileNode[] => {
  return nodes
    .filter(node => node.path !== targetPath && !node.path.startsWith(targetPath + '/'))
    .map(node => {
      if (node.children) {
        return {
          ...node,
          children: removeNodeFromTree(node.children, targetPath)
        };
      }
      return node;
    });
};

export const Sidebar: React.FC<SidebarProps> = ({ onFileSelect, selectedFile, socket }) => {
  const [files, setFiles] = useState<FileNode[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    'src': true,
    'services': true,
    'workspace': true
  });
  const [loading, setLoading] = useState(true);
  const [creatingType, setCreatingType] = useState<'file' | 'folder' | null>(null);
  const [newItemName, setNewItemName] = useState('');
  const [hoveredPath, setHoveredPath] = useState<string | null>(null);
  const [undoToast, setUndoToast] = useState<{ message: string; item?: DeletedItem } | null>(null);
  
  const deletedStackRef = useRef<DeletedItem[]>([]);
  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const fetchFiles = (isInitial = false) => {
    if (isInitial) setLoading(true);
    listFiles()
      .then(data => {
        setFiles(data || []);
        const initialExpanded: Record<string, boolean> = {};
        (data || []).forEach((node: FileNode) => {
          if (node.type === 'directory') initialExpanded[node.path] = true;
        });
        setExpanded(prev => ({ ...initialExpanded, ...prev }));
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load files:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchFiles(true);
  }, []);

  useEffect(() => {
    if (!socket) return;
    const onFilesChanged = () => fetchFiles(false);
    socket.on("files.changed", onFilesChanged);
    return () => {
      socket.off("files.changed", onFilesChanged);
    };
  }, [socket]);

  // Global Cmd+Z listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        if (deletedStackRef.current.length > 0) {
          e.preventDefault();
          handleUndoDelete();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const toggleExpand = (path: string) => {
    setExpanded(prev => ({ ...prev, [path]: !prev[path] }));
  };

  const handleCreate = async () => {
    if (!newItemName.trim()) {
      setCreatingType(null);
      return;
    }

    try {
      const path = newItemName.trim();
      if (creatingType === 'file') {
        await createFile(path);
      } else {
        await createFolder(path);
      }
      setNewItemName('');
      setCreatingType(null);
      fetchFiles();
    } catch (err) {
      console.error("Failed to create:", err);
    }
  };

  const showToast = (message: string, item?: DeletedItem) => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setUndoToast({ message, item });
    toastTimeoutRef.current = setTimeout(() => {
      setUndoToast(null);
    }, 4500);
  };

  const handleUndoDelete = async () => {
    const lastDeleted = deletedStackRef.current.pop();
    if (!lastDeleted) return;

    try {
      if (lastDeleted.isDirectory) {
        await createFolder(lastDeleted.path);
      } else {
        await createFile(lastDeleted.path);
        if (lastDeleted.content) {
          await saveFile(lastDeleted.path, lastDeleted.content);
        }
      }
      setUndoToast(null);
      fetchFiles();
    } catch (err) {
      console.error("Failed to restore file:", err);
    }
  };

  const handleDeleteItem = async (e: React.MouseEvent, path: string, isDirectory: boolean) => {
    e.stopPropagation();

    let savedContent = '';
    if (!isDirectory) {
      try {
        savedContent = await getFileContent(path);
      } catch {
        savedContent = '';
      }
    }

    const deletedItem: DeletedItem = {
      path,
      name: path.split('/').pop() || path,
      content: savedContent,
      isDirectory,
      timestamp: Date.now()
    };

    deletedStackRef.current.push(deletedItem);
    setFiles(prev => removeNodeFromTree(prev, path));
    showToast(`Deleted ${deletedItem.name}`, deletedItem);

    try {
      await deleteFile(path);
    } catch (err) {
      console.error("Failed to delete item:", err);
    }
  };

  const handleWipeWorkspace = async () => {
    if (window.confirm("⚠️ Reset Workspace: Are you sure you want to delete all files in this project?")) {
      setFiles([]);
      try {
        await resetWorkspace();
      } catch (err) {
        console.error("Failed to wipe workspace:", err);
      } finally {
        fetchFiles();
      }
    }
  };

  const renderTree = (nodes: FileNode[], depth = 0) => {
    return nodes.map((node) => {
      const isExpanded = expanded[node.path];
      const isSelected = selectedFile === node.path;
      const isHovered = hoveredPath === node.path;
      
      return (
        <div key={node.path} style={{ marginLeft: `${depth * 8}px` }}>
          <div 
            draggable={node.type === 'file'}
            onDragStart={(e) => {
              if (node.type === 'file') {
                e.dataTransfer.setData('text/plain', node.path);
                e.dataTransfer.setData('text/uri-list', node.path);
                e.dataTransfer.setData('application/x-ide-filepath', node.path);
                e.dataTransfer.effectAllowed = 'copy';
              }
            }}
            onClick={() => node.type === 'directory' ? toggleExpand(node.path) : onFileSelect(node.path)}
            onMouseEnter={() => setHoveredPath(node.path)}
            onMouseLeave={() => setHoveredPath(null)}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'space-between',
              padding: `3px ${tokens.spacing.sm}`, 
              cursor: node.type === 'file' ? 'grab' : 'pointer',
              backgroundColor: isSelected ? tokens.colors.accentSubtle : isHovered ? 'rgba(255,255,255,0.04)' : 'transparent',
              color: isSelected ? tokens.colors.textPrimary : tokens.colors.textMuted,
              fontSize: tokens.typography.secondary.fontSize,
              borderRadius: tokens.radii.sm,
              margin: '1px 2px',
              userSelect: 'none',
              transition: `background-color ${tokens.transitions.fast}`,
              borderLeft: isSelected ? `2px solid ${tokens.colors.accent}` : '2px solid transparent'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
              {node.type === 'directory' ? (
                <span style={{ display: 'flex', alignItems: 'center', marginRight: '4px' }}>
                  {isExpanded ? <ChevronDown size={13} color={tokens.colors.textDim} /> : <ChevronRight size={13} color={tokens.colors.textDim} />}
                  <Folder size={13} style={{ marginLeft: '2px', color: '#f59e0b' }} />
                </span>
              ) : (
                <span style={{ display: 'flex', alignItems: 'center', paddingLeft: '14px', marginRight: '4px' }}>
                  <FileCode size={13} color={isSelected ? tokens.colors.accent : tokens.colors.textDim} />
                </span>
              )}
              <span style={{ color: isSelected ? tokens.colors.textPrimary : tokens.colors.textMuted, fontWeight: isSelected ? 500 : 400 }}>
                {node.name}
              </span>
            </div>

            {/* Trash Delete on Hover */}
            {isHovered && (
              <button
                onClick={(e) => handleDeleteItem(e, node.path, node.type === 'directory')}
                title="Delete item (⌘Z to undo)"
                style={{
                  background: 'none',
                  border: 'none',
                  color: tokens.colors.textDim,
                  cursor: 'pointer',
                  padding: '2px',
                  borderRadius: '2px',
                  display: 'flex',
                  alignItems: 'center',
                  opacity: 0.8
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = tokens.colors.error; e.currentTarget.style.opacity = '1'; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = tokens.colors.textDim; e.currentTarget.style.opacity = '0.8'; }}
              >
                <Trash2 size={12} />
              </button>
            )}
          </div>

          {node.type === 'directory' && isExpanded && node.children && (
            <div>{renderTree(node.children, depth + 1)}</div>
          )}
        </div>
      );
    });
  };

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%', 
      backgroundColor: tokens.colors.surface2, 
      color: tokens.colors.textPrimary,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      position: 'relative'
    }}>
      
      {/* Explorer Header */}
      <div style={{ 
        height: '38px',
        padding: `0 ${tokens.spacing.md}`, 
        backgroundColor: tokens.colors.surface1, 
        borderBottom: `1px solid ${tokens.colors.border}`,
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        userSelect: 'none'
      }}>
        <span style={{ 
          fontSize: tokens.typography.meta.fontSize, 
          fontWeight: tokens.typography.header.fontWeight, 
          letterSpacing: '0.5px', 
          color: tokens.colors.textMuted 
        }}>
          EXPLORER
        </span>

        <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
          <button 
            onClick={() => setCreatingType('file')} 
            title="New File"
            style={{ background: 'none', border: 'none', color: tokens.colors.textMuted, cursor: 'pointer', padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }}
            onMouseEnter={(e) => e.currentTarget.style.color = tokens.colors.textPrimary}
            onMouseLeave={(e) => e.currentTarget.style.color = tokens.colors.textMuted}
          >
            <FilePlus size={14} />
          </button>
          
          <button 
            onClick={() => setCreatingType('folder')} 
            title="New Folder"
            style={{ background: 'none', border: 'none', color: tokens.colors.textMuted, cursor: 'pointer', padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }}
            onMouseEnter={(e) => e.currentTarget.style.color = tokens.colors.textPrimary}
            onMouseLeave={(e) => e.currentTarget.style.color = tokens.colors.textMuted}
          >
            <FolderPlus size={14} />
          </button>
          
          <button 
            onClick={fetchFiles} 
            title="Refresh Explorer"
            style={{ background: 'none', border: 'none', color: tokens.colors.textMuted, cursor: 'pointer', padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }}
            onMouseEnter={(e) => e.currentTarget.style.color = tokens.colors.textPrimary}
            onMouseLeave={(e) => e.currentTarget.style.color = tokens.colors.textMuted}
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>

          <button 
            onClick={handleWipeWorkspace} 
            title="Reset/Wipe Workspace Files"
            style={{ background: 'none', border: 'none', color: tokens.colors.textDim, cursor: 'pointer', padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }}
            onMouseEnter={(e) => e.currentTarget.style.color = tokens.colors.error}
            onMouseLeave={(e) => e.currentTarget.style.color = tokens.colors.textDim}
          >
            <AlertOctagon size={13} />
          </button>
        </div>
      </div>

      {/* Inline Creation Input */}
      {creatingType && (
        <div style={{ padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`, borderBottom: `1px solid ${tokens.colors.border}`, backgroundColor: tokens.colors.surface1 }}>
          <input
            autoFocus
            value={newItemName}
            onChange={(e) => setNewItemName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreate();
              if (e.key === 'Escape') setCreatingType(null);
            }}
            onBlur={handleCreate}
            placeholder={creatingType === 'file' ? "filename.tsx" : "folder_name"}
            style={{
              width: '100%',
              backgroundColor: tokens.colors.surface2,
              border: `1px solid ${tokens.colors.accent}`,
              borderRadius: tokens.radii.sm,
              color: tokens.colors.textPrimary,
              fontSize: tokens.typography.secondary.fontSize,
              padding: `3px ${tokens.spacing.sm}`,
              outline: 'none',
              boxSizing: 'border-box'
            }}
          />
        </div>
      )}

      {/* File Tree List or Consistent Empty State */}
      <div style={{ flex: 1, overflowY: 'auto', padding: `${tokens.spacing.xs} 0` }}>
        {loading ? (
          <PanelEmptyState icon={Folder} label="Loading Explorer..." loading={true} />
        ) : files.length === 0 ? (
          <PanelEmptyState 
            icon={Folder} 
            label="Workspace Empty" 
            description="Create a new file or ask the AI Engineer to build components."
            action={{ label: "New File", onClick: () => setCreatingType('file'), icon: FilePlus }}
          />
        ) : (
          renderTree(files)
        )}
      </div>

      {/* Undo Toast Notification */}
      {undoToast && (
        <div style={{
          position: 'absolute',
          bottom: tokens.spacing.md,
          left: tokens.spacing.sm,
          right: tokens.spacing.sm,
          backgroundColor: tokens.colors.surface1,
          border: `1px solid ${tokens.colors.borderStrong}`,
          borderRadius: tokens.radii.md,
          padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: '0 4px 14px rgba(0,0,0,0.4)',
          zIndex: 50,
          animation: 'fadeSlideUp 150ms ease-out'
        }}>
          <span style={{ fontSize: tokens.typography.meta.fontSize, color: tokens.colors.textPrimary }}>{undoToast.message}</span>
          <button
            onClick={handleUndoDelete}
            style={{
              background: tokens.colors.accent,
              color: '#ffffff',
              border: 'none',
              borderRadius: tokens.radii.sm,
              padding: `2px ${tokens.spacing.sm}`,
              fontSize: tokens.typography.meta.fontSize,
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            <RotateCcw size={11} />
            <span>Undo (⌘Z)</span>
          </button>
        </div>
      )}

    </div>
  );
};
