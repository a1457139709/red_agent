import { afterEach, describe, expect, it, vi } from "vitest";
import { backendHttpToWebSocketUrl, connectEventSocket, parseServerEventEnvelope } from "./ws";

class FakeSocket extends EventTarget {
  url: string;
  readyState: number = WebSocket.CONNECTING;
  send = vi.fn();
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

  it("includes replay scope query parameters when provided", () => {
    expect(
      backendHttpToWebSocketUrl("http://127.0.0.1:8000", {
        projectId: "project-1",
        sessionId: "session-1",
        authToken: "token-1",
        replayLimit: 20,
        sinceSequence: 9,
      }),
    ).toBe("ws://127.0.0.1:8000/ws/events?project_id=project-1&session_id=session-1&auth_token=token-1&limit=20&since_sequence=9");
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
  afterEach(() => {
    vi.useRealTimers();
  });

  it("reports connect, event, and disconnect states", () => {
    const statuses: string[] = [];
    const events: string[] = [];
    const errors: string[] = [];
    const sockets: FakeSocket[] = [];
    const controller = connectEventSocket(
      "ws://127.0.0.1:8000/ws/events",
      {
        onStatusChange: (status) => statuses.push(status),
        onEvent: (event) => events.push(event.event_kind),
        onError: (message) => errors.push(message),
      },
      (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket as unknown as WebSocket;
      },
    );

    sockets[0].readyState = WebSocket.OPEN;
    sockets[0].dispatchEvent(new Event("open"));
    sockets[0].dispatchEvent(
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
    controller.close();

    expect(statuses).toEqual(["connecting", "connected", "disconnected"]);
    expect(events).toEqual(["connection.connected"]);
    expect(errors).toEqual([]);
  });

  it("automatically reconnects after an unexpected close", () => {
    vi.useFakeTimers();
    const statuses: string[] = [];
    const sockets: FakeSocket[] = [];
    connectEventSocket(
      "ws://127.0.0.1:8000/ws/events",
      {
        onStatusChange: (status) => statuses.push(status),
        onEvent: vi.fn(),
        onError: vi.fn(),
      },
      (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket as unknown as WebSocket;
      },
      { reconnectDelaysMs: [25] },
    );

    sockets[0].readyState = WebSocket.OPEN;
    sockets[0].dispatchEvent(new Event("open"));
    sockets[0].dispatchEvent(new Event("close"));
    vi.advanceTimersByTime(25);

    expect(sockets).toHaveLength(2);
    expect(statuses).toEqual(["connecting", "connected", "reconnecting", "reconnecting"]);
  });

  it("supports manual reconnect", () => {
    const sockets: FakeSocket[] = [];
    const controller = connectEventSocket(
      "ws://127.0.0.1:8000/ws/events",
      {
        onStatusChange: vi.fn(),
        onEvent: vi.fn(),
        onError: vi.fn(),
      },
      (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket as unknown as WebSocket;
      },
    );

    controller.reconnect();

    expect(sockets).toHaveLength(2);
    expect(sockets[0].close).toHaveBeenCalled();
  });

  it("sends client messages through the active socket", () => {
    const sockets: FakeSocket[] = [];
    const controller = connectEventSocket(
      "ws://127.0.0.1:8000/ws/events",
      {
        onStatusChange: vi.fn(),
        onEvent: vi.fn(),
        onError: vi.fn(),
      },
      (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket as unknown as WebSocket;
      },
    );

    sockets[0].readyState = WebSocket.OPEN;
    expect(controller.send("terminal.input", {terminal_id: "term-1", data: "id\n"})).toBe(true);
    expect(sockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({event_kind: "terminal.input", payload: {terminal_id: "term-1", data: "id\n"}}),
    );
  });

  it("does not let a stale manual-reconnect close clear the active socket", () => {
    class AsyncCloseSocket extends FakeSocket {
      close = vi.fn();
      emitClose() {
        this.dispatchEvent(new Event("close"));
      }
    }
    const sockets: AsyncCloseSocket[] = [];
    const controller = connectEventSocket(
      "ws://127.0.0.1:8000/ws/events",
      {
        onStatusChange: vi.fn(),
        onEvent: vi.fn(),
        onError: vi.fn(),
      },
      (url) => {
        const socket = new AsyncCloseSocket(url);
        sockets.push(socket);
        return socket as unknown as WebSocket;
      },
    );

    controller.reconnect();
    sockets[0].emitClose();
    controller.close();

    expect(sockets).toHaveLength(2);
    expect(sockets[0].close).toHaveBeenCalledTimes(1);
    expect(sockets[1].close).toHaveBeenCalledTimes(1);
  });
});
