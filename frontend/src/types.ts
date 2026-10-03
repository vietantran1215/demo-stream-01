export type MessageStatus =
  | "normal"
  | "streaming"
  | "draft_pending"
  | "approved_sent"
  | "rejected";

export type ToolState = "started" | "progress" | "completed";

export type Message = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  status?: MessageStatus;
  toolName?: string;
  toolProgress?: number;
  toolState?: ToolState;
};

export type RouteName = "general" | "summarize" | "support_reply";

export type ApprovalRequest = {
  id: string;
  action: string;
  draft: string;
};

export type ToolEvent = {
  phase: ToolState;
  tool: string;
  message: string;
  progress: number;
};

export type StreamHandlers = {
  onToken: (content: string) => void;
  onRoute: (route: RouteName) => void;
  onTool: (event: ToolEvent) => void;
  onInterrupt: (approval: ApprovalRequest) => void;
  onDone: (interrupted: boolean) => void;
  onError: (message: string) => void;
};
