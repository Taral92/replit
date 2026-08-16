/**
 * Socket.IO singleton.
 *
 * Created at module scope rather than inside a component effect. React
 * StrictMode double-invokes effects in development, and socket.io's connect
 * handshake is async — the first connection often completes before the
 * cleanup's close() lands, leaving two live server-side sessions. Every
 * event then arrives twice and the agent panel shows duplicate rows.
 *
 * Module scope runs once per page load, so this cannot double-connect.
 */
import { io, Socket } from 'socket.io-client';

const API_URL =
  (import.meta as any).env.VITE_API_URL || 'http://localhost:8000';

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    socket = io(API_URL, {
      // Let socket.io reuse a single connection across HMR reloads.
      autoConnect: true,
      transports: ['websocket', 'polling'],
    });
  }
  return socket;
}
