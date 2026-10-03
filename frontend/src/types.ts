export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
};

export type RouteName = "general" | "summarize" | "support_reply";

export type ApprovalRequest = {
  id: string;
  action: string;
  draft: string;
};

export type StreamHandlers = {
  onToken: (content: string) => void;
  onRoute: (route: RouteName, expectedSkill: string | null) => void;
  onSkill: (name: string, source: string) => void;
  onSkillSkipped: (reason: string) => void;
  onNode: (name: string) => void;
  onInterrupt: (approval: ApprovalRequest) => void;
  onAction: (message: string) => void;
  onDone: (interrupted: boolean) => void;
  onError: (message: string) => void;
};
