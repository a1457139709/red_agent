import type { ServerEventEnvelope } from "./ws";

export type MessageRole = "agent" | "operator" | "system" | "execution";
export type ExecutionStepKind = "workflow" | "thinking" | "tool" | "command" | "result" | "plan" | "artifact" | "system";
export type ExecutionStatus = "running" | "completed" | "failed";

export type ExecutionStep = {
  id: string;
  kind: ExecutionStepKind;
  title: string;
  body: string;
  meta: string;
  eventKind: string;
  status?: string;
  chips?: string[];
};

export type ChatMessage = {
  id: string;
  role: MessageRole;
  title?: string;
  body: string;
  meta: string;
  eventKind: string;
  taskId: string | null;
  steps?: string[];
  executionSteps?: ExecutionStep[];
  executionStatus?: ExecutionStatus;
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
  return mapExecutionEvent(event);
}

export function appendChatMessage(current: ChatMessage[], message: ChatMessage): ChatMessage[] {
  if (message.role === "execution") {
    return appendExecutionMessage(current, message);
  }
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

function appendExecutionMessage(current: ChatMessage[], message: ChatMessage): ChatMessage[] {
  if (!message.taskId || !message.executionSteps?.length) {
    return [...current, message];
  }
  const existingIndex = current.findIndex((item) => item.role === "execution" && item.taskId === message.taskId);
  if (existingIndex === -1) {
    return [...current, message];
  }
  const existing = current[existingIndex];
  let steps = [...(existing.executionSteps ?? [])];
  const incomingStep = message.executionSteps[0];

  if (
    incomingStep.eventKind === "agent.summary" &&
    steps.some((step) => step.eventKind === "conversation.completed" && step.body === incomingStep.body)
  ) {
    return replaceAt(current, existingIndex, {
      ...existing,
      meta: message.meta,
      executionStatus: mergeExecutionStatus(existing.executionStatus, message.executionStatus),
    });
  }

  if (incomingStep.eventKind === "conversation.completed") {
    steps = steps.filter((step) => step.eventKind !== "conversation.delta");
  }

  const sameStepIndex = steps.findIndex((step) => step.id === incomingStep.id);
  if (sameStepIndex === -1) {
    steps.push(incomingStep);
  } else {
    steps = steps.map((step, index) => (index === sameStepIndex ? incomingStep : step));
  }

  const executionStatus = mergeExecutionStatus(existing.executionStatus, message.executionStatus);
  return replaceAt(current, existingIndex, {
    ...existing,
    body: executionBody(executionStatus),
    meta: message.meta,
    eventKind: message.eventKind,
    executionSteps: steps,
    executionStatus,
  });
}

function withEventSource(event: ServerEventEnvelope, message: Omit<ChatMessage, "eventKind" | "taskId">): ChatMessage {
  return {...message, eventKind: event.event_kind, taskId: event.task_id};
}

function replaceAt(messages: ChatMessage[], index: number, message: ChatMessage): ChatMessage[] {
  return messages.map((item, itemIndex) => (itemIndex === index ? message : item));
}

function mapExecutionEvent(event: ServerEventEnvelope): ChatMessage | null {
  const step = executionStepForEvent(event);
  if (step === null) {
    return null;
  }
  const status = executionStatusForEvent(event);
  return withEventSource(event, {
    id: event.task_id ? `execution-${event.task_id}` : event.event_id,
    role: "execution",
    title: "Execution steps",
    body: executionBody(status),
    meta: eventMeta(event),
    executionStatus: status,
    executionSteps: [step],
  });
}

function executionStepForEvent(event: ServerEventEnvelope): ExecutionStep | null {
  if (event.event_kind === "conversation.delta" || event.event_kind === "conversation.completed") {
    return {
      id: event.event_kind === "conversation.delta" ? `conversation-delta-${event.task_id ?? event.event_id}` : event.event_id,
      kind: "thinking",
      title: event.event_kind === "conversation.completed" ? "Agent response" : "Agent thinking",
      body: textPayload(event.payload.content) ?? summarizePayload(event.payload),
      meta: eventMeta(event),
      eventKind: event.event_kind,
    };
  }
  if (event.event_kind === "agent.summary") {
    const error = textPayload(event.payload.error);
    return {
      id: event.event_id,
      kind: error ? "result" : "thinking",
      title: error ? "Agent summary · recoverable" : "Agent summary",
      body: error ?? textPayload(event.payload.summary) ?? "Agent workflow summarized.",
      meta: eventMeta(event),
      eventKind: event.event_kind,
      status: error ? "recoverable" : undefined,
    };
  }
  if (event.event_kind === "agent.plan.created") {
    const nextActions = stringArrayPayload(event.payload.next_actions);
    return {
      id: event.event_id,
      kind: "plan",
      title: "Plan created",
      body: `Planned ${numberPayload(event.payload.dir_scan_count) ?? 0} directory scans and ${numberPayload(event.payload.poc_scan_count) ?? 0} POC scans.`,
      meta: eventMeta(event),
      eventKind: event.event_kind,
      chips: nextActions.length ? nextActions : undefined,
    };
  }
  if (event.event_kind === "agent.scan_summary") {
    return {
      id: event.event_id,
      kind: "result",
      title: "Scan summary",
      body: textPayload(event.payload.summary) ?? summarizePayload(event.payload),
      meta: eventMeta(event),
      eventKind: event.event_kind,
      chips: compactStrings([
        textPayload(event.payload.task_type),
        textPayload(event.payload.status),
        textPayload(event.payload.executor),
      ]),
    };
  }
  if (event.event_kind === "agent.next_action.suggested") {
    return {
      id: event.event_id,
      kind: "plan",
      title: "Next action",
      body: textPayload(event.payload.message) ?? summarizePayload(event.payload),
      meta: eventMeta(event),
      eventKind: event.event_kind,
    };
  }
  if (event.event_kind.startsWith("agent.tool.") || event.event_kind.startsWith("agent.tool_call.")) {
    return {
      id: event.event_id,
      kind: "tool",
      title: event.event_kind.endsWith(".started") ? "Tool started" : "Tool completed",
      body: toolEventBody(event),
      meta: eventMeta(event),
      eventKind: event.event_kind,
      status: textPayload(event.payload.status) ?? undefined,
      chips: compactStrings([textPayload(event.payload.status), textPayload(event.payload.reason)]),
    };
  }
  if (event.event_kind === "agent.terminal_command.suggested") {
    const command = textPayload(event.payload.command);
    return {
      id: event.event_id,
      kind: "command",
      title: "Terminal command",
      body: command ? `Suggested command: ${command}` : "Suggested a terminal command.",
      meta: eventMeta(event),
      eventKind: event.event_kind,
    };
  }
  if (event.event_kind === "report.generated") {
    return {
      id: event.event_id,
      kind: "artifact",
      title: "Report generated",
      body: textPayload(event.payload.summary) ?? textPayload(event.payload.public_id) ?? "Session writeup generated.",
      meta: eventMeta(event),
      eventKind: event.event_kind,
      chips: compactStrings([textPayload(event.payload.public_id), textPayload(event.payload.artifact_path)]),
    };
  }
  if (event.event_kind.startsWith("agent.workflow.")) {
    return {
      id: event.event_id,
      kind: "workflow",
      title: "Workflow",
      body: workflowBody(event),
      meta: eventMeta(event),
      eventKind: event.event_kind,
      status: textPayload(event.payload.status) ?? undefined,
    };
  }
  if (event.event_kind.startsWith("task.")) {
    return {
      id: event.event_id,
      kind: "result",
      title: taskStepTitle(event),
      body: taskEventBody(event),
      meta: eventMeta(event),
      eventKind: event.event_kind,
      status: taskStatus(event),
    };
  }
  return null;
}

function executionStatusForEvent(event: ServerEventEnvelope): ExecutionStatus {
  const status = textPayload(event.payload.status);
  if (event.event_kind.endsWith(".failed") || event.event_kind.endsWith(".cancelled") || status === "failed" || status === "cancelled") {
    return "failed";
  }
  if (event.event_kind === "agent.workflow.completed" || event.event_kind === "conversation.completed") {
    return "completed";
  }
  return "running";
}

function mergeExecutionStatus(current: ExecutionStatus | undefined, incoming: ExecutionStatus | undefined): ExecutionStatus {
  if (current === "failed" || incoming === "failed") {
    return "failed";
  }
  if (incoming === "completed") {
    return "completed";
  }
  return current ?? incoming ?? "running";
}

function executionBody(status: ExecutionStatus): string {
  if (status === "failed") {
    return "Agent execution needs attention.";
  }
  if (status === "completed") {
    return "Agent execution completed.";
  }
  return "Agent execution in progress.";
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

function taskStepTitle(event: ServerEventEnvelope): string {
  if (event.event_kind === "task.started") {
    return "Task started";
  }
  if (event.event_kind === "task.completed") {
    return "Task completed";
  }
  if (event.event_kind === "task.failed") {
    return "Task failed";
  }
  if (event.event_kind === "task.cancelled") {
    return "Task cancelled";
  }
  return "Task event";
}

function taskStatus(event: ServerEventEnvelope): string | undefined {
  if (event.event_kind === "task.completed") {
    return "succeeded";
  }
  if (event.event_kind === "task.failed") {
    return "failed";
  }
  if (event.event_kind === "task.cancelled") {
    return "cancelled";
  }
  return textPayload(event.payload.status) ?? undefined;
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
