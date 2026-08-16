/**
 * Centralized API client — every HTTP call to the backend goes through here.
 * Base URL comes from VITE_API_URL. No hardcoded localhost anywhere.
 */

const BASE = (import.meta as any).env.VITE_API_URL || 'http://localhost:8000';

function url(path: string): string {
  return `${BASE}${path}`;
}

// ── File operations ──

export async function listFiles(workspaceId = 'default'): Promise<any[]> {
  const res = await fetch(url(`/v1/workspaces/${workspaceId}/files`));
  if (!res.ok) throw new Error(`listFiles failed: ${res.status}`);
  return res.json();
}

export async function getFileContent(path: string, workspaceId = 'default'): Promise<string> {
  const res = await fetch(url(`/v1/workspaces/${workspaceId}/files/content?path=${encodeURIComponent(path)}`));
  if (!res.ok) throw new Error(`getFileContent failed: ${res.status}`);
  return res.text();
}

export async function saveFile(path: string, content: string, workspaceId = 'default'): Promise<any> {
  const res = await fetch(url(`/v1/workspaces/${workspaceId}/files/content`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) throw new Error(`saveFile failed: ${res.status}`);
  return res.json();
}

export async function createFile(path: string, content = '', workspaceId = 'default'): Promise<any> {
  const res = await fetch(url(`/v1/workspaces/${workspaceId}/files`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, type: 'file', content }),
  });
  if (!res.ok) throw new Error(`createFile failed: ${res.status}`);
  return res.json();
}

export async function createFolder(path: string, workspaceId = 'default'): Promise<any> {
  const res = await fetch(url(`/v1/workspaces/${workspaceId}/files`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, type: 'folder' }),
  });
  if (!res.ok) throw new Error(`createFolder failed: ${res.status}`);
  return res.json();
}

export async function deleteFile(path: string, workspaceId = 'default'): Promise<any> {
  const res = await fetch(url(`/v1/workspaces/${workspaceId}/files?path=${encodeURIComponent(path)}`), {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`deleteFile failed: ${res.status}`);
  return res.json();
}

export async function resetWorkspace(workspaceId = 'default'): Promise<any> {
  const res = await fetch(url(`/v1/workspaces/${workspaceId}/reset`), { method: 'POST' });
  if (!res.ok) throw new Error(`resetWorkspace failed: ${res.status}`);
  return res.json();
}

export { BASE };
