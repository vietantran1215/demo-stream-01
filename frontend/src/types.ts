export type MessageStatus =
  | "normal"
  | "streaming"
  | "draft_pending"
  | "approved_sent"
  | "rejected";

export type ToolState = "started" | "progress" | "completed";

export type Message = {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
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
  onRoute: (route: RouteName, expectedSkill: string | null) => void;
  onSkill: (name: string, source: string) => void;
  onSkillSkipped: (reason: string) => void;
  onTool: (event: ToolEvent) => void;
  onNode: (name: string) => void;
  onInterrupt: (approval: ApprovalRequest) => void;
  onAction: (message: string) => void;
  onDone: (interrupted: boolean) => void;
  onError: (message: string) => void;
};
