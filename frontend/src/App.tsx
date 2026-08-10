import { useState, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';

export default function App() {
  // Grab the replId from the URL or default to test-runner
  const params = new URLSearchParams(window.location.search);
  const replId = params.get('replId') || 'test-runner';
  
  // Connect to the specific pod via Ingress wildcard
  // Example: http://test-runner.localhost
  const wsUrl = `ws://${replId}.localhost`;
  
  const { socket, isConnected, send } = useWebSocket(wsUrl);
  
  const [inputMessage, setInputMessage] = useState('');
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    if (!socket) return;

    // Listen for the 'echo' event from our Node.js runner
    socket.on('echo', (data: any) => {
      setLogs((prev) => [...prev, `[ECHO RECEIVED] ${JSON.stringify(data)}`]);
    });

    return () => {
      socket.off('echo');
    };
  }, [socket]);

  const handleSend = () => {
    if (!inputMessage) return;
    
    // Log what we sent
    setLogs((prev) => [...prev, `[SENT] ${inputMessage}`]);
    
    // Send arbitrary event 'test-event' with the input payload
    send('test-event', { message: inputMessage });
    setInputMessage('');
  };

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <h1>Workspace Echo Tester</h1>
      <p>Target Pod: <strong>{replId}</strong></p>
      
      <div style={{ marginBottom: '20px', padding: '10px', border: `2px solid ${isConnected ? 'green' : 'red'}` }}>
        Status: {isConnected ? 'Connected 🟢' : 'Disconnected 🔴'}
      </div>

      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <input 
          type="text" 
          value={inputMessage} 
          onChange={(e) => setInputMessage(e.target.value)}
          placeholder="Type a message to send to the container..."
          style={{ flexGrow: 1, padding: '10px' }}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        />
        <button onClick={handleSend} style={{ padding: '10px 20px', cursor: 'pointer' }}>
          Send to Pod
        </button>
      </div>

      <div style={{ 
        background: 'black', 
        color: '#0f0', 
        padding: '20px', 
        height: '400px', 
        overflowY: 'auto',
        fontFamily: 'monospace' 
      }}>
        {logs.map((log, i) => (
          <div key={i}>{log}</div>
        ))}
        {logs.length === 0 && <div>Waiting for messages...</div>}
      </div>
    </div>
  );
}
