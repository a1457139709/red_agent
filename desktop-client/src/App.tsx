import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Activity, FolderKanban, RefreshCcw, Server, Wifi, WifiOff } from "lucide-react";
import { fetchHealth, getBackendUrl, type HealthStatus } from "./lib/api";
import {
  backendHttpToWebSocketUrl,
  connectEventSocket,
  type ServerEventEnvelope,
  type WebSocketStatus,
} from "./lib/ws";

const MAX_EVENTS = 20;

export function App() {
  const backendUrl = useMemo(() => getBackendUrl(), []);
  const wsUrl = useMemo(() => backendHttpToWebSocketUrl(backendUrl), [backendUrl]);
  const [health, setHealth] = useState<HealthStatus>({ state: "checking" });
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>("connecting");
  const [events, setEvents] = useState<ServerEventEnvelope[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refreshHealth = useCallback(async () => {
    setHealth({ state: "checking" });
    try {
      setHealth({ state: "online", payload: await fetchHealth(backendUrl) });
    } catch (healthError) {
      setHealth({
        state: "offline",
        error: healthError instanceof Error ? healthError.message : "Health check failed.",
      });
    }
  }, [backendUrl]);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  useEffect(() => {
    const socket = connectEventSocket(wsUrl, {
      onStatusChange: setWsStatus,
      onEvent: (event) => {
        setError(null);
        setEvents((current) => [event, ...current].slice(0, MAX_EVENTS));
      },
      onError: setError,
    });
    return () => socket.close();
  }, [wsUrl]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Activity aria-hidden="true" size={22} />
          <div>
            <h1>red-code</h1>
            <span>Control Center</span>
          </div>
        </div>
        <section className="panel project-panel" aria-labelledby="projects-heading">
          <div className="panel-title">
            <FolderKanban aria-hidden="true" size={18} />
            <h2 id="projects-heading">Projects</h2>
          </div>
          <div className="empty-list">
            <span>Project list placeholder</span>
          </div>
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Backend</p>
            <strong>{backendUrl}</strong>
          </div>
          <button type="button" className="icon-button" onClick={refreshHealth} aria-label="Refresh health">
            <RefreshCcw aria-hidden="true" size={18} />
          </button>
        </header>

        <section className="status-grid" aria-label="Connection status">
          <StatusPanel
            icon={<Server aria-hidden="true" size={20} />}
            title="HTTP health"
            status={health.state}
            detail={health.state === "online" ? health.payload.started_at : health.state === "offline" ? health.error : "Checking"}
          />
          <StatusPanel
            icon={wsStatus === "connected" ? <Wifi aria-hidden="true" size={20} /> : <WifiOff aria-hidden="true" size={20} />}
            title="WebSocket"
            status={wsStatus}
            detail={wsUrl}
          />
        </section>

        <section className="panel event-panel" aria-labelledby="events-heading">
          <div className="panel-title">
            <Activity aria-hidden="true" size={18} />
            <h2 id="events-heading">Event log</h2>
          </div>
          {error ? <p className="error-line">{error}</p> : null}
          <div className="event-list">
            {events.length === 0 ? (
              <div className="empty-list">
                <span>No server events yet</span>
              </div>
            ) : (
              events.map((event) => (
                <article className="event-row" key={event.event_id}>
                  <span className="sequence">#{event.sequence}</span>
                  <div>
                    <strong>{event.event_kind}</strong>
                    <p>{event.timestamp}</p>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

type StatusPanelProps = {
  icon: ReactNode;
  title: string;
  status: string;
  detail: string;
};

function StatusPanel({ icon, title, status, detail }: StatusPanelProps) {
  return (
    <article className="panel status-panel">
      <div className="status-heading">
        {icon}
        <span>{title}</span>
      </div>
      <strong className={`status-value status-${status}`}>{status}</strong>
      <p>{detail}</p>
    </article>
  );
}
