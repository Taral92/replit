import { useWebSocket } from './hooks/useWebSocket';
import { Terminal } from './components/Terminal';

export default function App() {
  // Grab the replId from the URL or default to test-runner
  const params = new URLSearchParams(window.location.search);
  const replId = params.get('replId') || 'test-runner';
  
  // Connect to the specific pod via Ingress wildcard
  const wsUrl = `ws://${replId}.localhost`;
  
  const { socket, isConnected } = useWebSocket(wsUrl);
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', backgroundColor: '#1e1e1e', color: 'white', fontFamily: 'sans-serif' }}>
      <header style={{ padding: '10px 20px', borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontWeight: 'bold', marginRight: '15px' }}>RunnerIDE</span>
          <span style={{ fontSize: '0.9em', color: '#888' }}>Workspace: {replId}</span>
        </div>
        <div style={{ fontSize: '0.9em', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: isConnected ? '#4caf50' : '#f44336' }} />
          {isConnected ? 'Connected' : 'Disconnected'}
        </div>
      </header>
      
      <main style={{ flexGrow: 1, overflow: 'hidden', padding: '10px' }}>
        {socket && isConnected ? (
          <Terminal socket={socket} />
        ) : (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: '#888' }}>
            Connecting to workspace...
          </div>
        )}
      </main>
    </div>
  );
}
