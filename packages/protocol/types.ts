export interface BaseEvent {
  type: string;
  request_id: string;
  workspace_id: string;
  session_id?: string;
  timestamp: string;
}

// Session Events
export interface SessionConnectedEvent extends BaseEvent {
  type: 'session.connected';
  user_id?: string;
}

export interface SessionDisconnectedEvent extends BaseEvent {
  type: 'session.disconnected';
}

// Terminal Events
export interface TerminalInputEvent extends BaseEvent {
  type: 'terminal.input';
  data: string;
}

export interface TerminalOutputEvent extends BaseEvent {
  type: 'terminal.output';
  data: string;
}

export interface TerminalResizeEvent extends BaseEvent {
  type: 'terminal.resize';
  cols: number;
  rows: number;
}

// Agent Events
export interface AgentStartEvent extends BaseEvent {
  type: 'agent.start';
  prompt: string;
}

export interface AgentStatusEvent extends BaseEvent {
  type: 'agent.status';
  status: string;
  phase?: 'EXPLORE' | 'PLAN' | 'IMPLEMENT' | 'VERIFY' | 'DONE';
}

export interface AgentMessageEvent extends BaseEvent {
  type: 'agent.message';
  role: 'assistant' | 'system' | 'user';
  content: string;
}

export interface AgentToolStartedEvent extends BaseEvent {
  type: 'agent.tool.started';
  tool_name: string;
  arguments: Record<string, any>;
}

export interface AgentToolCompletedEvent extends BaseEvent {
  type: 'agent.tool.completed';
  tool_name: string;
  result: any;
  duration_ms: number;
  diff?: string;
  added: number;
  removed: number;
}

export interface AgentToolFailedEvent extends BaseEvent {
  type: 'agent.tool.failed';
  tool_name: string;
  error: string;
  duration_ms: number;
}

// Workspace & File Events
export interface FileItem {
  name: string;
  type: 'file' | 'directory';
  path: string;
  children?: FileItem[];
}

export interface FileReadRequest extends BaseEvent {
  type: 'file.read';
  path: string;
}

export interface FileWriteRequest extends BaseEvent {
  type: 'file.write';
  path: string;
  content: string;
}

export interface FilePatchRequest extends BaseEvent {
  type: 'file.patch';
  path: string;
  target_content: string;
  replacement_content: string;
}

export interface FileEvent extends BaseEvent {
  type: 'file.created' | 'file.updated' | 'file.deleted';
  path: string;
}

// Process Events
export type ProcessStatus = 'STARTING' | 'RUNNING' | 'STOPPED' | 'FAILED';

export interface ProcessStartRequest extends BaseEvent {
  type: 'process.start';
  command: string;
  cwd?: string;
}

export interface ProcessStopRequest extends BaseEvent {
  type: 'process.stop';
  process_id: string;
}

export interface ProcessEvent extends BaseEvent {
  type: 'process.started' | 'process.exited' | 'process.failed';
  process_id: string;
  command: string;
  pid?: number;
  status: ProcessStatus;
  exit_code?: number;
}

// Preview & Port Events
export interface PortUpdateEvent extends BaseEvent {
  type: 'preview.ports_updated';
  ports: string[];
}

export interface PreviewReadyEvent extends BaseEvent {
  type: 'preview.ready';
  port: string;
  url: string;
}

// Approval & Error Events
export type RiskLevel = 'safe' | 'restricted' | 'destructive' | 'privileged';

export interface ApprovalRequiredEvent extends BaseEvent {
  type: 'approval.required';
  action_id: string;
  operation: string;
  command_or_path: string;
  risk_level: RiskLevel;
  description: string;
}

export interface ApprovalResponseEvent extends BaseEvent {
  type: 'approval.response';
  action_id: string;
  approved: boolean;
}

export interface ErrorEvent extends BaseEvent {
  type: 'error';
  message: string;
  code?: string;
  details?: Record<string, any>;
}

export type IDEEvent =
  | SessionConnectedEvent
  | SessionDisconnectedEvent
  | TerminalInputEvent
  | TerminalOutputEvent
  | TerminalResizeEvent
  | AgentStartEvent
  | AgentStatusEvent
  | AgentMessageEvent
  | AgentToolStartedEvent
  | AgentToolCompletedEvent
  | AgentToolFailedEvent
  | FileReadRequest
  | FileWriteRequest
  | FilePatchRequest
  | FileEvent
  | ProcessStartRequest
  | ProcessStopRequest
  | ProcessEvent
  | PortUpdateEvent
  | PreviewReadyEvent
  | ApprovalRequiredEvent
  | ApprovalResponseEvent
  | ErrorEvent;
