export type ServerEventEnvelope = {
  event_id: string;
  project_id: string | null;
  session_id: string | null;
  task_id: string | null;
  sequence: number;
  event_kind: string;
  timestamp: string;
  payload: Record<string, unknown>;
};

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

export function backendHttpToWebSocketUrl(baseUrl: string): string {
  const url = new URL(baseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/events";
  url.search = "";
  url.hash = "";
  return url.toString();
}

export function parseServerEventEnvelope(payload: unknown): ServerEventEnvelope {
  if (typeof payload !== "object" || payload === null) {
    throw new Error("Invalid server event envelope.");
  }
  const envelope = payload as Record<string, unknown>;
  if (
    typeof envelope.event_id !== "string" ||
    typeof envelope.sequence !== "number" ||
    typeof envelope.event_kind !== "string" ||
    typeof envelope.timestamp !== "string" ||
    typeof envelope.payload !== "object" ||
    envelope.payload === null
  ) {
    throw new Error("Invalid server event envelope fields.");
  }
  return envelope as ServerEventEnvelope;
}

export type EventSocketHandlers = {
  onStatusChange: (status: WebSocketStatus) => void;
  onEvent: (event: ServerEventEnvelope) => void;
  onError: (message: string) => void;
};

export function connectEventSocket(
  url: string,
  handlers: EventSocketHandlers,
  socketFactory: (url: string) => WebSocket = (targetUrl) => new WebSocket(targetUrl),
): WebSocket {
  handlers.onStatusChange("connecting");
  const socket = socketFactory(url);

  socket.addEventListener("open", () => handlers.onStatusChange("connected"));
  socket.addEventListener("close", () => handlers.onStatusChange("disconnected"));
  socket.addEventListener("error", () => {
    handlers.onStatusChange("error");
    handlers.onError("WebSocket connection failed.");
  });
  socket.addEventListener("message", (event) => {
    try {
      handlers.onEvent(parseServerEventEnvelope(JSON.parse(event.data)));
    } catch (error) {
      handlers.onError(error instanceof Error ? error.message : "Invalid WebSocket message.");
    }
  });

  return socket;
}
