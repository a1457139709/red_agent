import { describe, expect, it, vi } from "vitest";
import { backendHttpToWebSocketUrl, connectEventSocket, parseServerEventEnvelope } from "./ws";

class FakeSocket extends EventTarget {
  url: string;
  close = vi.fn(() => this.dispatchEvent(new Event("close")));

  constructor(url: string) {
    super();
    this.url = url;
  }
}

describe("backendHttpToWebSocketUrl", () => {
  it("maps http backend URLs to ws event URLs", () => {
    expect(backendHttpToWebSocketUrl("http://127.0.0.1:8000")).toBe("ws://127.0.0.1:8000/ws/events");
  });

  it("maps https backend URLs to wss event URLs", () => {
    expect(backendHttpToWebSocketUrl("https://example.test/api")).toBe("wss://example.test/ws/events");
  });
});

describe("parseServerEventEnvelope", () => {
  it("parses a connected event envelope", () => {
    expect(
      parseServerEventEnvelope({
        event_id: "event-1",
        project_id: null,
        session_id: null,
        task_id: null,
        sequence: 1,
        event_kind: "connection.connected",
        timestamp: "2026-05-03T00:00:00+00:00",
        payload: { message: "connected" },
      }),
    ).toMatchObject({ event_kind: "connection.connected", sequence: 1 });
  });
});

describe("connectEventSocket", () => {
  it("reports connect, event, and disconnect states", () => {
    const statuses: string[] = [];
    const events: string[] = [];
    const errors: string[] = [];
    const socket = connectEventSocket(
      "ws://127.0.0.1:8000/ws/events",
      {
        onStatusChange: (status) => statuses.push(status),
        onEvent: (event) => events.push(event.event_kind),
        onError: (message) => errors.push(message),
      },
      (url) => new FakeSocket(url) as unknown as WebSocket,
    ) as unknown as FakeSocket;

    socket.dispatchEvent(new Event("open"));
    socket.dispatchEvent(
      new MessageEvent("message", {
        data: JSON.stringify({
          event_id: "event-1",
          project_id: null,
          session_id: null,
          task_id: null,
          sequence: 1,
          event_kind: "connection.connected",
          timestamp: "2026-05-03T00:00:00+00:00",
          payload: {},
        }),
      }),
    );
    socket.close();

    expect(statuses).toEqual(["connecting", "connected", "disconnected"]);
    expect(events).toEqual(["connection.connected"]);
    expect(errors).toEqual([]);
  });
});
