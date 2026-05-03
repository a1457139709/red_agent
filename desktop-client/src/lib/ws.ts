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

export type WebSocketStatus = "connecting" | "connected" | "reconnecting" | "disconnected" | "error";

const DEFAULT_RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000];

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

export type EventSocketOptions = {
  reconnectDelaysMs?: number[];
};

export type EventSocketController = {
  reconnect: () => void;
  close: () => void;
};

export function connectEventSocket(
  url: string,
  handlers: EventSocketHandlers,
  socketFactory: (url: string) => WebSocket = (targetUrl) => new WebSocket(targetUrl),
  options: EventSocketOptions = {},
): EventSocketController {
  const reconnectDelaysMs = options.reconnectDelaysMs?.length
    ? options.reconnectDelaysMs
    : DEFAULT_RECONNECT_DELAYS_MS;
  let socket: WebSocket | null = null;
  let closedByClient = false;
  const ignoredCloseSockets = new WeakSet<WebSocket>();
  let reconnectAttempt = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const clearReconnectTimer = () => {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  const openSocket = (status: WebSocketStatus) => {
    clearReconnectTimer();
    handlers.onStatusChange(status);
    const currentSocket = socketFactory(url);
    socket = currentSocket;

    currentSocket.addEventListener("open", () => {
      if (socket !== currentSocket) {
        return;
      }
      reconnectAttempt = 0;
      handlers.onStatusChange("connected");
    });
    currentSocket.addEventListener("close", () => {
      if (socket === currentSocket) {
        socket = null;
      }
      if (ignoredCloseSockets.has(currentSocket)) {
        return;
      }
      if (socket !== null) {
        return;
      }
      if (closedByClient) {
        handlers.onStatusChange("disconnected");
        return;
      }
      scheduleReconnect();
    });
    currentSocket.addEventListener("error", () => {
      if (socket !== currentSocket) {
        return;
      }
      handlers.onStatusChange("error");
      handlers.onError("WebSocket connection failed.");
    });
    currentSocket.addEventListener("message", (event) => {
      if (socket !== currentSocket) {
        return;
      }
      try {
        handlers.onEvent(parseServerEventEnvelope(JSON.parse(event.data)));
      } catch (error) {
        handlers.onError(error instanceof Error ? error.message : "Invalid WebSocket message.");
      }
    });
  };

  const scheduleReconnect = () => {
    const delayIndex = Math.min(reconnectAttempt, reconnectDelaysMs.length - 1);
    const delayMs = reconnectDelaysMs[delayIndex];
    reconnectAttempt += 1;
    handlers.onStatusChange("reconnecting");
    reconnectTimer = setTimeout(() => openSocket("reconnecting"), delayMs);
  };

  const closeCurrentSocket = (ignoreCloseEvent: boolean) => {
    if (socket !== null) {
      const currentSocket = socket;
      socket = null;
      if (ignoreCloseEvent) {
        ignoredCloseSockets.add(currentSocket);
      }
      currentSocket.close();
    }
  };

  openSocket("connecting");

  return {
    reconnect: () => {
      closedByClient = false;
      reconnectAttempt = 0;
      clearReconnectTimer();
      closeCurrentSocket(true);
      openSocket("connecting");
    },
    close: () => {
      closedByClient = true;
      clearReconnectTimer();
      closeCurrentSocket(true);
      handlers.onStatusChange("disconnected");
    },
  };
}
