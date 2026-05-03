import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Activity, FolderKanban, RefreshCcw, Server, Target, Wifi, WifiOff } from "lucide-react";
import {
  createProject,
  createTargetSession,
  fetchHealth,
  getBackendUrl,
  getSessionDashboard,
  listProjectSessions,
  listProjects,
  type HealthStatus,
  type ProjectDto,
  type SessionDashboardDto,
  type TargetSessionDto,
  type TargetType,
} from "./lib/api";
import { TARGET_TYPE_OPTIONS, validateProjectForm, validateTargetSessionForm } from "./lib/forms";
import { parseWorkspaceHash, projectHash, sessionHash } from "./lib/routes";
import {
  backendHttpToWebSocketUrl,
  connectEventSocket,
  type ServerEventEnvelope,
  type WebSocketStatus,
} from "./lib/ws";

const MAX_EVENTS = 20;

type LoadState = "idle" | "loading" | "error";

export function App() {
  const backendUrl = useMemo(() => getBackendUrl(), []);
  const wsUrl = useMemo(() => backendHttpToWebSocketUrl(backendUrl), [backendUrl]);
  const [health, setHealth] = useState<HealthStatus>({state: "checking"});
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>("connecting");
  const [events, setEvents] = useState<ServerEventEnvelope[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [sessions, setSessions] = useState<TargetSessionDto[]>([]);
  const [dashboard, setDashboard] = useState<SessionDashboardDto | null>(null);
  const [route, setRoute] = useState(() => parseWorkspaceHash(window.location.hash));
  const [projectLoadState, setProjectLoadState] = useState<LoadState>("idle");
  const [sessionLoadState, setSessionLoadState] = useState<LoadState>("idle");
  const [projectForm, setProjectForm] = useState({name: "", description: ""});
  const [sessionForm, setSessionForm] = useState({
    name: "",
    target_value: "",
    target_type: "ip" as TargetType,
    summary: "",
  });
  const [projectFormError, setProjectFormError] = useState<string | null>(null);
  const [sessionFormError, setSessionFormError] = useState<string | null>(null);

  const selectedProject = projects.find((project) => project.id === route.projectId || project.public_id === route.projectId) ?? null;
  const selectedSession = sessions.find((session) => session.id === route.sessionId || session.public_id === route.sessionId) ?? null;

  const refreshHealth = useCallback(async () => {
    setHealth({state: "checking"});
    try {
      setHealth({state: "online", payload: await fetchHealth(backendUrl)});
    } catch (healthError) {
      setHealth({
        state: "offline",
        error: healthError instanceof Error ? healthError.message : "Health check failed.",
      });
    }
  }, [backendUrl]);

  const refreshProjects = useCallback(async () => {
    setProjectLoadState("loading");
    try {
      const loadedProjects = await listProjects(backendUrl);
      setProjects(loadedProjects);
      setProjectLoadState("idle");
      if (!route.projectId && loadedProjects.length > 0) {
        window.location.hash = projectHash(loadedProjects[0].id);
      }
    } catch (projectError) {
      setProjectLoadState("error");
      setError(projectError instanceof Error ? projectError.message : "Failed to load projects.");
    }
  }, [backendUrl, route.projectId]);

  const refreshSessions = useCallback(async () => {
    if (!selectedProject) {
      setSessions([]);
      setDashboard(null);
      return;
    }
    setSessionLoadState("loading");
    try {
      const loadedSessions = await listProjectSessions(backendUrl, selectedProject.id);
      setSessions(loadedSessions);
      setSessionLoadState("idle");
    } catch (sessionError) {
      setSessionLoadState("error");
      setError(sessionError instanceof Error ? sessionError.message : "Failed to load sessions.");
    }
  }, [backendUrl, selectedProject]);

  const refreshDashboard = useCallback(async () => {
    if (!selectedSession) {
      setDashboard(null);
      return;
    }
    try {
      setDashboard(await getSessionDashboard(backendUrl, selectedSession.id));
    } catch (dashboardError) {
      setDashboard(null);
      setError(dashboardError instanceof Error ? dashboardError.message : "Failed to load dashboard.");
    }
  }, [backendUrl, selectedSession]);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  useEffect(() => {
    const updateRoute = () => setRoute(parseWorkspaceHash(window.location.hash));
    window.addEventListener("hashchange", updateRoute);
    updateRoute();
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  useEffect(() => {
    const controller = connectEventSocket(wsUrl, {
      onStatusChange: setWsStatus,
      onEvent: (event) => {
        setError(null);
        setEvents((current) => [event, ...current].slice(0, MAX_EVENTS));
      },
      onError: setError,
    });
    const reconnect = () => controller.reconnect();
    window.addEventListener("red-code:ws-reconnect", reconnect);
    return () => {
      window.removeEventListener("red-code:ws-reconnect", reconnect);
      controller.close();
    };
  }, [wsUrl]);

  const submitProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validationError = validateProjectForm(projectForm);
    if (validationError) {
      setProjectFormError(validationError);
      return;
    }
    setProjectFormError(null);
    try {
      const project = await createProject(backendUrl, {
        name: projectForm.name.trim(),
        description: projectForm.description.trim() || null,
      });
      setProjects((current) => [project, ...current]);
      setProjectForm({name: "", description: ""});
      window.location.hash = projectHash(project.id);
    } catch (submitError) {
      setProjectFormError(submitError instanceof Error ? submitError.message : "Failed to create project.");
    }
  };

  const submitSession = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProject) {
      return;
    }
    const validationError = validateTargetSessionForm(sessionForm);
    if (validationError) {
      setSessionFormError(validationError);
      return;
    }
    setSessionFormError(null);
    try {
      const session = await createTargetSession(backendUrl, selectedProject.id, {
        name: sessionForm.name.trim(),
        target_value: sessionForm.target_value.trim(),
        target_type: sessionForm.target_type,
        summary: sessionForm.summary.trim() || null,
      });
      setSessions((current) => [session, ...current]);
      setSessionForm({name: "", target_value: "", target_type: "ip", summary: ""});
      window.location.hash = sessionHash(selectedProject.id, session.id);
    } catch (submitError) {
      setSessionFormError(submitError instanceof Error ? submitError.message : "Failed to create session.");
    }
  };

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
          <form className="stack-form" onSubmit={submitProject}>
            <label>
              <span>Name</span>
              <input
                value={projectForm.name}
                onChange={(event) => setProjectForm((current) => ({...current, name: event.target.value}))}
              />
            </label>
            <label>
              <span>Description</span>
              <textarea
                rows={2}
                value={projectForm.description}
                onChange={(event) => setProjectForm((current) => ({...current, description: event.target.value}))}
              />
            </label>
            {projectFormError ? <p className="error-line compact">{projectFormError}</p> : null}
            <button type="submit" className="primary-button">Create Project</button>
          </form>
          <NavList
            emptyLabel={projectLoadState === "loading" ? "Loading projects" : "No projects"}
            items={projects.map((project) => ({
              id: project.id,
              label: project.name,
              meta: project.public_id,
              selected: selectedProject?.id === project.id,
              onClick: () => {
                window.location.hash = projectHash(project.id);
              },
            }))}
          />
        </section>

        <section className="panel" aria-labelledby="sessions-heading">
          <div className="panel-title">
            <Target aria-hidden="true" size={18} />
            <h2 id="sessions-heading">Sessions</h2>
          </div>
          {selectedProject ? (
            <>
              <form className="stack-form" onSubmit={submitSession}>
                <label>
                  <span>Name</span>
                  <input
                    value={sessionForm.name}
                    onChange={(event) => setSessionForm((current) => ({...current, name: event.target.value}))}
                  />
                </label>
                <label>
                  <span>Target</span>
                  <input
                    value={sessionForm.target_value}
                    onChange={(event) => setSessionForm((current) => ({...current, target_value: event.target.value}))}
                  />
                </label>
                <label>
                  <span>Type</span>
                  <select
                    value={sessionForm.target_type}
                    onChange={(event) =>
                      setSessionForm((current) => ({...current, target_type: event.target.value as TargetType}))
                    }
                  >
                    {TARGET_TYPE_OPTIONS.map((targetType) => (
                      <option value={targetType} key={targetType}>{targetType}</option>
                    ))}
                  </select>
                </label>
                {sessionFormError ? <p className="error-line compact">{sessionFormError}</p> : null}
                <button type="submit" className="primary-button">Create Session</button>
              </form>
              <NavList
                emptyLabel={sessionLoadState === "loading" ? "Loading sessions" : "No sessions"}
                items={sessions.map((session) => ({
                  id: session.id,
                  label: session.name,
                  meta: `${session.target_type} ${session.target_value}`,
                  selected: selectedSession?.id === session.id,
                  onClick: () => {
                    window.location.hash = sessionHash(selectedProject.id, session.id);
                  },
                }))}
              />
            </>
          ) : (
            <div className="empty-list"><span>No project selected</span></div>
          )}
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Backend</p>
            <strong>{backendUrl}</strong>
          </div>
          <div className="toolbar">
            <button type="button" className="icon-button" onClick={refreshHealth} aria-label="Refresh health">
              <RefreshCcw aria-hidden="true" size={18} />
            </button>
          </div>
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
            actionLabel="Reconnect"
            onAction={() => {
              window.dispatchEvent(new CustomEvent("red-code:ws-reconnect"));
            }}
          />
        </section>

        <section className="workspace-grid">
          <section className="panel dashboard-panel" aria-labelledby="dashboard-heading">
            <div className="panel-title">
              <Target aria-hidden="true" size={18} />
              <h2 id="dashboard-heading">Workspace</h2>
            </div>
            {dashboard ? (
              <DashboardView dashboard={dashboard} />
            ) : selectedProject ? (
              <ProjectEmptyState project={selectedProject} />
            ) : (
              <div className="empty-list"><span>Create or select a project</span></div>
            )}
          </section>

          <section className="panel event-panel" aria-labelledby="events-heading">
            <div className="panel-title">
              <Activity aria-hidden="true" size={18} />
              <h2 id="events-heading">Event log</h2>
            </div>
            {error ? <p className="error-line">{error}</p> : null}
            <div className="event-list">
              {events.length === 0 ? (
                <div className="empty-list"><span>No server events yet</span></div>
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
      </section>
    </main>
  );
}

type StatusPanelProps = {
  icon: ReactNode;
  title: string;
  status: string;
  detail: string;
  actionLabel?: string;
  onAction?: () => void;
};

function StatusPanel({icon, title, status, detail, actionLabel, onAction}: StatusPanelProps) {
  return (
    <article className="panel status-panel">
      <div className="status-heading">
        {icon}
        <span>{title}</span>
      </div>
      <strong className={`status-value status-${status}`}>{status}</strong>
      <p>{detail}</p>
      {actionLabel && onAction ? (
        <button type="button" className="text-button" onClick={onAction}>{actionLabel}</button>
      ) : null}
    </article>
  );
}

type NavListItem = {
  id: string;
  label: string;
  meta: string;
  selected: boolean;
  onClick: () => void;
};

function NavList({items, emptyLabel}: { items: NavListItem[]; emptyLabel: string }) {
  if (items.length === 0) {
    return <div className="empty-list compact-empty"><span>{emptyLabel}</span></div>;
  }
  return (
    <div className="nav-list">
      {items.map((item) => (
        <button
          type="button"
          className={`nav-row ${item.selected ? "selected" : ""}`}
          key={item.id}
          onClick={item.onClick}
        >
          <strong>{item.label}</strong>
          <span>{item.meta}</span>
        </button>
      ))}
    </div>
  );
}

function ProjectEmptyState({project}: { project: ProjectDto }) {
  return (
    <div className="dashboard-body">
      <div>
        <p className="eyebrow">Project</p>
        <h3>{project.name}</h3>
        <p>{project.description ?? "No description"}</p>
      </div>
      <MetricGrid metrics={[["Sessions", "0"], ["Tasks", "0"], ["Findings", "0"], ["Flags", "0"]]} />
    </div>
  );
}

function DashboardView({dashboard}: { dashboard: SessionDashboardDto }) {
  return (
    <div className="dashboard-body">
      <div>
        <p className="eyebrow">Target</p>
        <h3>{dashboard.session.name}</h3>
        <p>{dashboard.target.type} {dashboard.target.value}</p>
      </div>
      <MetricGrid
        metrics={[
          ["Open ports", String(dashboard.open_ports.length)],
          ["Web entries", String(dashboard.web_entries.length)],
          ["Evidence", String(dashboard.evidence_count)],
          ["Flags", String(dashboard.flag_count)],
        ]}
      />
      <div className="empty-list dashboard-empty">
        <span>Empty session dashboard</span>
      </div>
    </div>
  );
}

function MetricGrid({metrics}: { metrics: [string, string][] }) {
  return (
    <div className="metric-grid">
      {metrics.map(([label, value]) => (
        <div className="metric" key={label}>
          <strong>{value}</strong>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}
