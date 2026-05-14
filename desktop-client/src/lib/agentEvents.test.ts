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
      role: "agent",
      title: "Plan created",
      steps: ["Review HTTP service"],
    });
    expect(mapServerEventToChatMessage(event("agent.scan_summary", {summary: "nmap found 2 open ports"}))).toMatchObject({
      title: "Scan summary",
      body: "nmap found 2 open ports",
    });
    expect(mapServerEventToChatMessage(event("agent.tool.completed", {tool: "start_port_scan", status: "succeeded"}))).toMatchObject({
      title: "Tool completed",
      body: "start_port_scan succeeded.",
    });
    expect(
      mapServerEventToChatMessage(event("agent.tool_call.completed", {tool: "start_port_scan", status: "succeeded", summary: "Started port scan."})),
    ).toMatchObject({
      title: "Tool completed",
      body: "Started port scan.",
    });
    expect(mapServerEventToChatMessage(event("conversation.completed", {content: "I am red-code."}))).toMatchObject({
      title: "Agent response",
      body: "I am red-code.",
    });
    expect(mapServerEventToChatMessage(event("agent.next_action.suggested", {message: "Run ffuf"}))).toMatchObject({
      title: "Next action",
      body: "Run ffuf",
    });
    expect(mapServerEventToChatMessage(event("task.completed", {summary: "scan complete"}))).toMatchObject({
      role: "system",
      body: "scan complete",
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
      eventKind: "conversation.completed",
      title: "Agent response",
      body: "I am red-code.",
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
