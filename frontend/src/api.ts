import type {
  ApprovalRequest,
  RouteName,
  StreamHandlers,
  ToolEvent,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type RawSseEvent = {
  event: string;
  data: unknown;
};

function parseFrame(frame: string): RawSseEvent | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: JSON.parse(dataLines.join("\n")),
  };
}

function dispatch(event: RawSseEvent, handlers: StreamHandlers): void {
  const data = event.data as Record<string, unknown>;

  switch (event.event) {
    case "token":
      handlers.onToken(String(data.content ?? ""));
      break;
    case "route":
      handlers.onRoute(
        String(data.route ?? "general") as RouteName,
        data.expected_skill == null ? null : String(data.expected_skill),
      );
      break;
    case "skill":
      handlers.onSkill(
        String(data.name ?? "unknown"),
        String(data.source ?? "unknown"),
      );
      break;
    case "skill_skipped":
      handlers.onSkillSkipped(
        String(data.reason ?? "No specialized skill required."),
      );
      break;
    case "tool": {
      const toolEvent: ToolEvent = {
        phase: String(data.phase ?? "progress") as ToolEvent["phase"],
        tool: String(data.tool ?? "unknown_tool"),
        message: String(data.message ?? "Tool is running"),
        progress: Number(data.progress ?? 0),
      };
      handlers.onTool(toolEvent);
      break;
    }
    case "interrupt": {
      const value = (data.value ?? {}) as Record<string, unknown>;
      const approval: ApprovalRequest = {
        id: String(data.id ?? ""),
        action: String(value.action ?? "unknown"),
        draft: String(value.draft ?? ""),
      };
      handlers.onInterrupt(approval);
      break;
    }
    case "done":
      handlers.onDone(Boolean(data.interrupted));
      break;
    case "error": {
      const message = String(data.message ?? "Unknown server error");
      handlers.onError(message);

      // SSE errors arrive inside an HTTP 200 stream. Throw so callers do not
      // mistake a failed graph/action for a successful resume.
      throw new Error(message);
    }
  }
}

async function streamRequest(
  url: string,
  body: unknown,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }

  if (!response.body) {
    throw new Error("Streaming response body is unavailable in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();

    if (done) {
      buffer += decoder.decode();
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const parsed = parseFrame(frame);
      if (parsed) {
        dispatch(parsed, handlers);
      }
    }
  }

  if (buffer.trim()) {
    const parsed = parseFrame(buffer);
    if (parsed) {
      dispatch(parsed, handlers);
    }
  }
}

export async function sendMessage(
  threadId: string,
  message: string,
  handlers: StreamHandlers,
): Promise<void> {
  return streamRequest(
    `${API_BASE_URL}/api/chat/${encodeURIComponent(threadId)}`,
    { message },
    handlers,
  );
}

export async function resumeThread(
  threadId: string,
  approved: boolean,
  handlers: StreamHandlers,
): Promise<void> {
  return streamRequest(
    `${API_BASE_URL}/api/chat/${encodeURIComponent(threadId)}/resume`,
    { approved },
    handlers,
  );
}
