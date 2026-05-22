import { describe, expect, it } from "vitest";
import { appendChatMessage, type ChatMessage, mapServerEventToChatMessage } from "./agentEvents";
import type { ServerEventEnvelope } from "./ws";

describe("mapServerEventToChatMessage", () => {
  it("maps operator, plan, scan summary, tool, next action, and task events", () => {
    expect(mapServerEventToChatMessage(event("agent.message.received", {message: "enumerate target"}))).toMatchObject({
      role: "operator",
      body: "enumerate target",
    });
    expect(
      mapServerEventToChatMessage(event("agent.plan.created", {
        dir_scan_count: 1,
        poc_scan_count: 2,
        next_actions: ["Review HTTP service"],
      })),
    ).toMatchObject({
      role: "execution",
      title: "Execution steps",
      executionSteps: [{
        kind: "plan",
        title: "Plan created",
        chips: ["Review HTTP service"],
      }],
    });
    expect(mapServerEventToChatMessage(event("agent.scan_summary", {summary: "nmap found 2 open ports"}))).toMatchObject({
      role: "execution",
      executionSteps: [{
        kind: "result",
        title: "Scan summary",
        body: "nmap found 2 open ports",
      }],
    });
    expect(mapServerEventToChatMessage(event("agent.tool.completed", {tool: "start_port_scan", status: "succeeded"}))).toMatchObject({
      role: "execution",
      executionSteps: [{
        kind: "tool",
        title: "Tool completed",
        body: "start_port_scan succeeded.",
      }],
    });
    expect(
      mapServerEventToChatMessage(event("agent.tool_call.completed", {tool: "start_port_scan", status: "succeeded", summary: "Started port scan."})),
    ).toMatchObject({
      role: "execution",
      executionSteps: [{
        kind: "tool",
        title: "Tool completed",
        body: "Started port scan.",
      }],
    });
    expect(mapServerEventToChatMessage(event("conversation.completed", {content: "I am red-code."}))).toMatchObject({
      role: "execution",
      executionSteps: [{
        kind: "thinking",
        title: "Agent response",
        body: "I am red-code.",
      }],
    });
    expect(mapServerEventToChatMessage(event("agent.next_action.suggested", {message: "Run ffuf"}))).toMatchObject({
      role: "execution",
      executionSteps: [{
        kind: "plan",
        title: "Next action",
        body: "Run ffuf",
      }],
    });
    expect(mapServerEventToChatMessage(event("task.completed", {summary: "scan complete"}))).toMatchObject({
      role: "execution",
      executionSteps: [{
        kind: "result",
        title: "Task completed",
        body: "scan complete",
      }],
    });
  });

  it("ignores connection and terminal output events", () => {
    expect(mapServerEventToChatMessage(event("connection.connected", {}))).toBeNull();
    expect(mapServerEventToChatMessage(event("terminal.output", {chunk: "ok"}))).toBeNull();
  });

  it("keeps one visible agent answer for delta, completed, and matching summary events", () => {
    const delta = mapServerEventToChatMessage(event("conversation.delta", {content: "I am red-code."}));
    const completed = mapServerEventToChatMessage(event("conversation.completed", {content: "I am red-code."}));
    const summary = mapServerEventToChatMessage(event("agent.summary", {summary: "I am red-code."}));

    expect(delta).not.toBeNull();
    expect(completed).not.toBeNull();
    expect(summary).not.toBeNull();

    const messages = [delta, completed, summary].reduce<ChatMessage[]>(
      (current, message) => (message ? appendChatMessage(current, message) : current),
      [],
    );

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      role: "execution",
      eventKind: "conversation.completed",
      title: "Execution steps",
      body: "Agent execution completed.",
      executionSteps: [{
        eventKind: "conversation.completed",
        title: "Agent response",
        body: "I am red-code.",
      }],
    });
  });

  it("collapses same-task execution events into one visible step block", () => {
    const events = [
      event("agent.workflow.started", {status: "running"}),
      event("agent.tool_call.started", {tool: "propose_target"}),
      event("agent.tool_call.completed", {tool: "propose_target", status: "succeeded", summary: "Target accepted."}),
      event("agent.terminal_command.suggested", {command: "which nmap"}),
      event("task.failed", {summary: "nmap binary was not found."}),
      event("conversation.completed", {content: "The port scan attempt failed because nmap is missing."}),
    ];

    const messages = events
      .map(mapServerEventToChatMessage)
      .reduce<ChatMessage[]>((current, message) => (message ? appendChatMessage(current, message) : current), []);

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      role: "execution",
      taskId: "task-1",
      body: "Agent execution needs attention.",
      executionStatus: "failed",
      executionSteps: [
        {kind: "workflow", title: "Workflow"},
        {kind: "tool", title: "Tool started"},
        {kind: "tool", title: "Tool completed"},
        {kind: "command", title: "Terminal command"},
        {kind: "result", title: "Task failed", status: "failed"},
        {kind: "thinking", title: "Agent response"},
      ],
    });
  });
});

function event(eventKind: string, payload: Record<string, unknown>): ServerEventEnvelope {
  return {
    event_id: `${eventKind}-1`,
    project_id: "project-1",
    session_id: "session-1",
    task_id: "task-1",
    sequence: 1,
    event_kind: eventKind,
    timestamp: "2026-05-03T00:00:00+00:00",
    payload,
  };
}
