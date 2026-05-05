import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Activity, FolderKanban, ListChecks, Play, RefreshCcw, Server, Target, Wifi, WifiOff, Wrench } from "lucide-react";
import {
  cancelScanTask,
  createProject,
  createScanTask,
  createTargetSession,
  fetchHealth,
  getBackendUrl,
  getSessionDashboard,
  listSessionTasks,
  listToolStatus,
  listProjectSessions,
  listProjects,
  rerunScanTask,
  type HealthStatus,
  type ProjectDto,
  type ScanTaskDto,
  type SessionDashboardDto,
  type TargetSessionDto,
  type TargetType,
  type ToolStatusDto,
} from "./lib/api";
import { SCAN_TASK_OPTIONS, TARGET_TYPE_OPTIONS, validateProjectForm, validateScanTaskForm, validateTargetSessionForm } from "./lib/forms";
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
  const [health, setHealth] = useState<HealthStatus>({state: "checking"});
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>("connecting");
  const [events, setEvents] = useState<ServerEventEnvelope[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [sessions, setSessions] = useState<TargetSessionDto[]>([]);
  const [dashboard, setDashboard] = useState<SessionDashboardDto | null>(null);
  const [toolStatus, setToolStatus] = useState<ToolStatusDto[]>([]);
  const [tasks, setTasks] = useState<ScanTaskDto[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [route, setRoute] = useState(() => parseWorkspaceHash(window.location.hash));
  const [projectLoadState, setProjectLoadState] = useState<LoadState>("idle");
  const [sessionLoadState, setSessionLoadState] = useState<LoadState>("idle");
  const [taskLoadState, setTaskLoadState] = useState<LoadState>("idle");
  const [projectForm, setProjectForm] = useState({name: "", description: ""});
  const [sessionForm, setSessionForm] = useState({
    name: "",
    target_value: "",
    target_type: "ip" as TargetType,
    summary: "",
  });
  const [scanForm, setScanForm] = useState({
    task_type: "port_scan",
    target: "",
    ports: "1,22,80,443,8080",
    wordlist: "",
    templates: "",
  });
  const [projectFormError, setProjectFormError] = useState<string | null>(null);
  const [sessionFormError, setSessionFormError] = useState<string | null>(null);
  const [scanFormError, setScanFormError] = useState<string | null>(null);

  const selectedProject = projects.find((project) => project.id === route.projectId || project.public_id === route.projectId) ?? null;
  const selectedSession = sessions.find((session) => session.id === route.sessionId || session.public_id === route.sessionId) ?? null;
  const selectedTask = tasks.find((task) => task.id === selectedTaskId || task.public_id === selectedTaskId) ?? tasks[0] ?? null;
  const wsUrl = useMemo(
    () =>
      backendHttpToWebSocketUrl(backendUrl, {
        projectId: selectedProject?.id ?? null,
        sessionId: selectedSession?.id ?? null,
        replay: selectedSession !== null,
        replayLimit: MAX_EVENTS,
      }),
    [backendUrl, selectedProject?.id, selectedSession?.id],
  );

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

  const refreshTools = useCallback(async () => {
    try {
      setToolStatus(await listToolStatus(backendUrl));
    } catch (toolError) {
      setError(toolError instanceof Error ? toolError.message : "Failed to load tool status.");
    }
  }, [backendUrl]);

  const refreshTasks = useCallback(async () => {
    if (!selectedSession) {
      setTasks([]);
      setSelectedTaskId(null);
      return;
    }
    setTaskLoadState("loading");
    try {
      const loadedTasks = await listSessionTasks(backendUrl, selectedSession.id);
      setTasks(loadedTasks);
      setTaskLoadState("idle");
      setSelectedTaskId((current) => current ?? loadedTasks[0]?.id ?? null);
    } catch (taskError) {
      setTaskLoadState("error");
      setError(taskError instanceof Error ? taskError.message : "Failed to load tasks.");
    }
  }, [backendUrl, selectedSession]);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  useEffect(() => {
    void refreshTools();
  }, [refreshTools]);

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
    void refreshTasks();
  }, [refreshTasks]);

  useEffect(() => {
    setEvents([]);
    const controller = connectEventSocket(wsUrl, {
      onStatusChange: setWsStatus,
      onEvent: (event) => {
        setError(null);
        setEvents((current) => mergeEvents(current, event));
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

  const submitScanTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedSession) {
      return;
    }
    const effectiveScanForm = {
      ...scanForm,
      target: scanForm.target.trim() || selectedSession.target_value,
    };
    const validationError = validateScanTaskForm(effectiveScanForm);
    if (validationError) {
      setScanFormError(validationError);
      return;
    }
    setScanFormError(null);
    try {
      const task = await createScanTask(backendUrl, selectedSession.id, {
        task_type: effectiveScanForm.task_type as "port_scan" | "dir_scan" | "poc_scan",
        input: buildScanInput(effectiveScanForm),
      });
      setTasks((current) => [task, ...current]);
      setSelectedTaskId(task.id);
      await refreshDashboard();
    } catch (submitError) {
      setScanFormError(submitError instanceof Error ? submitError.message : "Failed to create scan task.");
    }
  };

  const updateTask = (updated: ScanTaskDto) => {
    setTasks((current) => current.map((task) => (task.id === updated.id ? updated : task)));
    setSelectedTaskId(updated.id);
  };

  const cancelSelectedTask = async () => {
    if (!selectedTask) {
      return;
    }
    try {
      updateTask(await cancelScanTask(backendUrl, selectedTask.id));
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Failed to cancel task.");
    }
  };

  const rerunSelectedTask = async () => {
    if (!selectedTask) {
      return;
    }
    try {
      const task = await rerunScanTask(backendUrl, selectedTask.id);
      setTasks((current) => [task, ...current]);
      setSelectedTaskId(task.id);
      await refreshDashboard();
    } catch (rerunError) {
      setError(rerunError instanceof Error ? rerunError.message : "Failed to rerun task.");
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
          <section className="panel scan-panel" aria-labelledby="scan-heading">
            <div className="panel-title">
              <Play aria-hidden="true" size={18} />
              <h2 id="scan-heading">Scan Tasks</h2>
            </div>
            {selectedSession ? (
              <form className="scan-form" onSubmit={submitScanTask}>
                <label>
                  <span>Type</span>
                  <select
                    value={scanForm.task_type}
                    onChange={(event) => setScanForm((current) => ({...current, task_type: event.target.value}))}
                  >
                    {SCAN_TASK_OPTIONS.map((taskType) => (
                      <option value={taskType} key={taskType}>{taskType}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Target</span>
                  <input
                    value={scanForm.target}
                    placeholder={selectedSession.target_value}
                    onChange={(event) => setScanForm((current) => ({...current, target: event.target.value}))}
                  />
                </label>
                {scanForm.task_type === "port_scan" ? (
                  <label>
                    <span>Ports</span>
                    <input
                      value={scanForm.ports}
                      onChange={(event) => setScanForm((current) => ({...current, ports: event.target.value}))}
                    />
                  </label>
                ) : null}
                {scanForm.task_type === "dir_scan" ? (
                  <label>
                    <span>Wordlist</span>
                    <input
                      value={scanForm.wordlist}
                      onChange={(event) => setScanForm((current) => ({...current, wordlist: event.target.value}))}
                    />
                  </label>
                ) : null}
                {scanForm.task_type === "poc_scan" ? (
                  <label>
                    <span>Templates</span>
                    <input
                      value={scanForm.templates}
                      onChange={(event) => setScanForm((current) => ({...current, templates: event.target.value}))}
                    />
                  </label>
                ) : null}
                {scanFormError ? <p className="error-line compact">{scanFormError}</p> : null}
                <button type="submit" className="primary-button">Start Scan</button>
              </form>
            ) : (
              <div className="empty-list"><span>Select a session to create scan tasks</span></div>
            )}
          </section>

          <section className="panel tool-panel" aria-labelledby="tools-heading">
            <div className="panel-title">
              <Wrench aria-hidden="true" size={18} />
              <h2 id="tools-heading">Tool Status</h2>
            </div>
            <ToolStatusList tools={toolStatus} />
          </section>

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

          <section className="panel task-panel" aria-labelledby="tasks-heading">
            <div className="panel-title">
              <ListChecks aria-hidden="true" size={18} />
              <h2 id="tasks-heading">Task Queue</h2>
            </div>
            <TaskQueue
              tasks={tasks}
              selectedTask={selectedTask}
              emptyLabel={taskLoadState === "loading" ? "Loading tasks" : "No scan tasks"}
              onSelect={(task) => setSelectedTaskId(task.id)}
              onCancel={cancelSelectedTask}
              onRerun={rerunSelectedTask}
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
                <div className="empty-list"><span>No server events yet</span></div>
              ) : (
                events.map((event) => (
                  <article className="event-row" key={event.event_id}>
                    <span className="sequence">#{event.sequence}</span>
                    <div>
                      <strong>{event.event_kind}</strong>
                      <p>{event.timestamp}</p>
                      <p>{formatEventPayload(event.payload)}</p>
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
  const hasDashboardContent = [
    dashboard.open_ports.length,
    dashboard.web_entries.length,
    dashboard.directory_findings.length,
    dashboard.poc_hits.length,
    dashboard.attack_path.length,
    dashboard.recent_commands.length,
    dashboard.evidence.length,
    dashboard.flags.length,
    dashboard.next_actions.length,
  ].some((count) => count > 0);

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
        {!hasDashboardContent ? (
          <span>Empty session dashboard</span>
        ) : (
          <ResultTables dashboard={dashboard} />
        )}
      </div>
    </div>
  );
}

function ToolStatusList({tools}: { tools: ToolStatusDto[] }) {
  if (tools.length === 0) {
    return <div className="empty-list compact-empty"><span>No tool status loaded</span></div>;
  }
  return (
    <div className="tool-list">
      {tools.map((tool) => (
        <div className="tool-row" key={tool.name}>
          <strong>{tool.name}</strong>
          <span className={tool.available ? "status-online" : "status-offline"}>
            {tool.available ? "available" : "missing"}
          </span>
          <p>{tool.version ?? tool.error ?? tool.path ?? "No details"}</p>
        </div>
      ))}
    </div>
  );
}

type TaskQueueProps = {
  tasks: ScanTaskDto[];
  selectedTask: ScanTaskDto | null;
  emptyLabel: string;
  onSelect: (task: ScanTaskDto) => void;
  onCancel: () => void;
  onRerun: () => void;
};

function TaskQueue({tasks, selectedTask, emptyLabel, onSelect, onCancel, onRerun}: TaskQueueProps) {
  if (tasks.length === 0) {
    return <div className="empty-list"><span>{emptyLabel}</span></div>;
  }
  return (
    <div className="task-layout">
      <div className="task-list">
        {tasks.map((task) => (
          <button
            type="button"
            className={`task-row ${selectedTask?.id === task.id ? "selected" : ""}`}
            key={task.id}
            onClick={() => onSelect(task)}
          >
            <strong>{task.task_type}</strong>
            <span>{task.executor} · {task.status}</span>
          </button>
        ))}
      </div>
      {selectedTask ? <TaskDetail task={selectedTask} onCancel={onCancel} onRerun={onRerun} /> : null}
    </div>
  );
}

function TaskDetail({task, onCancel, onRerun}: { task: ScanTaskDto; onCancel: () => void; onRerun: () => void }) {
  const result = task.result;
  const structured = isRecord(result.structured) ? result.structured : {};
  const artifacts = Array.isArray(result.artifacts) ? result.artifacts.filter(isRecord) : [];
  return (
    <div className="task-detail">
      <div className="task-actions">
        <button type="button" className="text-button" onClick={onRerun}>Rerun</button>
        <button type="button" className="text-button" onClick={onCancel}>Cancel</button>
      </div>
      <p>{typeof result.summary === "string" ? result.summary : task.error ?? "No summary"}</p>
      <pre>{JSON.stringify(structured, null, 2)}</pre>
      <div className="artifact-list">
        {artifacts.map((artifact) => (
          <a href={`file://${String(artifact.path)}`} key={`${artifact.kind}-${artifact.path}`}>
            {String(artifact.kind)}: {String(artifact.path)}
          </a>
        ))}
      </div>
    </div>
  );
}

function ResultTables({dashboard}: { dashboard: SessionDashboardDto }) {
  return (
    <div className="result-tables">
      <MiniTable title="Open Ports" rows={dashboard.open_ports} columns={["port", "protocol", "service"]} />
      <MiniTable title="Web Entries" rows={dashboard.web_entries} columns={["url", "scheme", "source"]} />
      <MiniTable title="Web Paths" rows={dashboard.directory_findings} columns={["status", "url"]} />
      <MiniTable title="POC Hits" rows={dashboard.poc_hits} columns={["severity", "template_id", "matched_url"]} />
      <MiniTable title="Attack Path" rows={dashboard.attack_path} columns={["stage", "title", "status", "next_action"]} />
      <MiniTable title="Next Actions" rows={dashboard.next_actions} columns={["stage", "title", "next_action"]} />
      <MiniTable title="Recent Commands" rows={dashboard.recent_commands} columns={["command", "exit_code", "terminal_id", "created_at"]} />
      <MiniTable title="Evidence" rows={dashboard.evidence} columns={["evidence_type", "title", "summary", "created_at"]} />
      <MiniTable title="Flags" rows={dashboard.flags} columns={["flag_type", "value", "created_at"]} />
    </div>
  );
}

function MiniTable({title, rows, columns}: { title: string; rows: Record<string, unknown>[]; columns: string[] }) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <div className="mini-table">
      <strong>{title}</strong>
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${title}-${index}`}>
              {columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
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

function buildScanInput(input: {
  task_type: string;
  target: string;
  ports: string;
  wordlist: string;
  templates: string;
}): Record<string, unknown> {
  const target = input.target.trim();
  if (input.task_type === "port_scan") {
    return {
      target_host: target,
      ports: input.ports.trim() ? input.ports.split(",").map((port) => Number(port.trim())) : [],
    };
  }
  if (input.task_type === "dir_scan") {
    return {base_url: target, wordlist: input.wordlist.trim(), filters: {}};
  }
  return {
    target_url: target,
    templates: input.templates.trim() ? input.templates.split(",").map((template) => template.trim()) : undefined,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function mergeEvents(current: ServerEventEnvelope[], incoming: ServerEventEnvelope): ServerEventEnvelope[] {
  const deduped = [incoming, ...current.filter((event) => event.event_id !== incoming.event_id)];
  return deduped.slice(0, MAX_EVENTS);
}

function formatEventPayload(payload: Record<string, unknown>): string {
  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message;
  }
  const serialized = JSON.stringify(payload);
  return serialized === "{}" ? "No payload" : serialized;
}
