import { useState, useEffect } from 'react';
import { io, Socket } from 'socket.io-client';

export function useWebSocket(url: string) {
    const [socket, setSocket] = useState<Socket | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    useEffect(() => {
        if (!url) return;

        // Note: For actual cloud, this would be wss:// and match the ingress
        console.log(`Connecting to WebSocket: ${url}`);
        const newSocket = io(url, {
            transports: ['websocket'],
            // In a real app we'd pass JWT auth tokens here
        });

        newSocket.on('connect', () => {
            console.log('Connected to Workspace Runner!');
            setIsConnected(true);
        });

        newSocket.on('disconnect', () => {
            console.log('Disconnected from Workspace Runner.');
            setIsConnected(false);
        });

        setSocket(newSocket);

        return () => {
            newSocket.disconnect();
        };
    }, [url]);

    const send = (eventName: string, payload: any) => {
        if (socket && isConnected) {
            socket.emit(eventName, payload);
        } else {
            console.error("Cannot send, socket not connected.");
        }
    };

    return { socket, isConnected, send };
}
