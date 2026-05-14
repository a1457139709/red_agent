import type { ServerEventEnvelope } from "./ws";

export type MessageRole = "agent" | "operator" | "system";

export type ChatMessage = {
  id: string;
  role: MessageRole;
  title?: string;
  body: string;
  meta: string;
  eventKind: string;
  taskId: string | null;
  steps?: string[];
};

export function mapServerEventToChatMessage(event: ServerEventEnvelope): ChatMessage | null {
  if (event.event_kind === "connection.connected" || event.event_kind === "terminal.output") {
    return null;
  }
  if (event.event_kind === "agent.message.received") {
    return withEventSource(event, {
      id: event.event_id,
      role: "operator",
      title: "Operator",
      body: textPayload(event.payload.message) ?? "Agent message received.",
      meta: eventMeta(event),
    });
  }
  if (event.event_kind === "conversation.delta" || event.event_kind === "conversation.completed") {
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: event.event_kind === "conversation.completed" ? "Agent response" : "Agent",
      body: textPayload(event.payload.content) ?? summarizePayload(event.payload),
      meta: eventMeta(event),
    });
  }
  if (event.event_kind === "agent.summary") {
    const error = textPayload(event.payload.error);
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: error ? "Agent summary · recoverable" : "Agent summary",
      body: error ?? textPayload(event.payload.summary) ?? "Agent workflow summarized.",
      meta: eventMeta(event),
    });
  }
  if (event.event_kind === "agent.plan.created") {
    const nextActions = stringArrayPayload(event.payload.next_actions);
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: "Plan created",
      body: `Planned ${numberPayload(event.payload.dir_scan_count) ?? 0} directory scans and ${numberPayload(event.payload.poc_scan_count) ?? 0} POC scans.`,
      meta: eventMeta(event),
      steps: nextActions.length ? nextActions : undefined,
    });
  }
  if (event.event_kind === "agent.scan_summary") {
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: "Scan summary",
      body: textPayload(event.payload.summary) ?? summarizePayload(event.payload),
      meta: eventMeta(event),
      steps: compactStrings([
        textPayload(event.payload.task_type),
        textPayload(event.payload.status),
        textPayload(event.payload.executor),
      ]),
    });
  }
  if (event.event_kind === "agent.next_action.suggested") {
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: "Next action",
      body: textPayload(event.payload.message) ?? summarizePayload(event.payload),
      meta: eventMeta(event),
    });
  }
  if (event.event_kind.startsWith("agent.tool.") || event.event_kind.startsWith("agent.tool_call.")) {
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: event.event_kind.endsWith(".started") ? "Tool started" : "Tool completed",
      body: toolEventBody(event),
      meta: eventMeta(event),
      steps: compactStrings([textPayload(event.payload.status), textPayload(event.payload.reason)]),
    });
  }
  if (event.event_kind === "agent.terminal_command.suggested") {
    const command = textPayload(event.payload.command);
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: "Terminal command",
      body: command ? `Suggested command: ${command}` : "Suggested a terminal command.",
      meta: eventMeta(event),
    });
  }
  if (event.event_kind === "report.generated") {
    return withEventSource(event, {
      id: event.event_id,
      role: "agent",
      title: "Report generated",
      body: textPayload(event.payload.summary) ?? textPayload(event.payload.public_id) ?? "Session writeup generated.",
      meta: eventMeta(event),
      steps: compactStrings([textPayload(event.payload.public_id), textPayload(event.payload.artifact_path)]),
    });
  }
  if (event.event_kind.startsWith("agent.workflow.")) {
    return withEventSource(event, {
      id: event.event_id,
      role: "system",
      body: workflowBody(event),
      meta: eventMeta(event),
    });
  }
  if (event.event_kind.startsWith("task.")) {
    return withEventSource(event, {
      id: event.event_id,
      role: "system",
      body: taskEventBody(event),
      meta: eventMeta(event),
    });
  }
  return null;
}

export function appendChatMessage(current: ChatMessage[], message: ChatMessage): ChatMessage[] {
  if (message.eventKind === "conversation.delta") {
    const existingDeltaIndex = current.findIndex((item) => (
      item.eventKind === "conversation.delta" && item.taskId === message.taskId
    ));
    if (existingDeltaIndex === -1) {
      return [...current, message];
    }
    return replaceAt(current, existingDeltaIndex, message);
  }
  if (message.eventKind === "conversation.completed") {
    return [
      ...current.filter((item) => !(
        item.eventKind === "conversation.delta" && item.taskId === message.taskId
      )),
      message,
    ];
  }
  if (
    message.eventKind === "agent.summary" &&
    current.some((item) => (
      item.eventKind === "conversation.completed" &&
      item.taskId === message.taskId &&
      item.body === message.body
    ))
  ) {
    return current;
  }
  return [...current, message];
}

function withEventSource(event: ServerEventEnvelope, message: Omit<ChatMessage, "eventKind" | "taskId">): ChatMessage {
  return {...message, eventKind: event.event_kind, taskId: event.task_id};
}

function replaceAt(messages: ChatMessage[], index: number, message: ChatMessage): ChatMessage[] {
  return messages.map((item, itemIndex) => (itemIndex === index ? message : item));
}

function eventMeta(event: ServerEventEnvelope): string {
  const time = compactTime(event.timestamp);
  const task = event.task_id ? ` · ${event.task_id.slice(0, 8)}` : "";
  return `${event.event_kind}${task} · ${time}`;
}

function workflowBody(event: ServerEventEnvelope): string {
  const status = textPayload(event.payload.status);
  if (event.event_kind === "agent.workflow.queued") {
    return "Agent workflow queued.";
  }
  if (event.event_kind === "agent.workflow.started") {
    return "Agent workflow started.";
  }
  return `Agent workflow ${status ?? event.event_kind.replace("agent.workflow.", "")}.`;
}

function taskEventBody(event: ServerEventEnvelope): string {
  const summary = textPayload(event.payload.summary);
  if (summary) {
    return summary;
  }
  const taskType = textPayload(event.payload.task_type);
  const executor = textPayload(event.payload.executor);
  const reason = textPayload(event.payload.reason);
  return compactStrings([taskType, executor, reason])?.join(" · ") || event.event_kind;
}

function toolEventBody(event: ServerEventEnvelope): string {
  const tool = textPayload(event.payload.tool) ?? "agent tool";
  const status = textPayload(event.payload.status);
  if (event.event_kind.endsWith(".started")) {
    return `${tool} started.`;
  }
  return textPayload(event.payload.summary) ?? `${tool} ${status ?? "completed"}.`;
}

function summarizePayload(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined)
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return entries.join(" · ") || "Event recorded.";
}

function compactTime(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return "-";
  }
  return new Date(timestamp).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
}

function textPayload(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberPayload(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function stringArrayPayload(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim() !== "") : [];
}

function compactStrings(values: Array<string | null>): string[] | undefined {
  const filtered = values.filter((value): value is string => value !== null && value.trim() !== "");
  return filtered.length ? filtered : undefined;
}
