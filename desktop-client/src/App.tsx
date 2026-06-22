import { Component, FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Bot,
  CheckCircle2,
  ClipboardList,
  Command,
  Download,
  FileText,
  Layers3,
  Menu,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Radio,
  RotateCcw,
  Save,
  SendHorizontal,
  Settings,
  ShieldCheck,
  Target,
  X,
} from "lucide-react";
import {
  type EvidenceDto,
  type FindingDto,
  type ProjectDto,
  type ReportDto,
  type TargetDto,
  type TargetSessionDto,
  type ToolConfigDto,
  type ToolStatusDto,
  createEvidence,
  createProject,
  createProjectReport,
  createSessionReport,
  createTargetSession,
  getApiAuthToken,
  getAuthSession,
  getBackendUrl,
  getToolConfig,
  isLocalBackendUrl,
  listEvidence,
  listFindings,
  listProjectReports,
  listProjectSessions,
  listProjectTargets,
  listProjects,
  listSessionReports,
  listToolStatus,
  login,
  logout,
  reportDownloadUrl,
  sendAgentMessage,
  setApiAuthToken,
  setBackendUrl,
  updateToolConfig,
} from "./lib/api";
import { validateAgentMessageForm, validateProjectForm } from "./lib/forms";
import { appendChatMessage, type ChatMessage, mapServerEventToChatMessage } from "./lib/agentEvents";
import { backendHttpToWebSocketUrl, connectEventSocket } from "./lib/ws";

type WorkspaceMode = "Recon" | "Exploit" | "Report" | "Settings";

type ProjectGroup = {
  project: ProjectDto;
  sessions: TargetSessionDto[];
};

type EvidenceItem = {
  id: string;
  kind: string;
  title: string;
  summary: string;
};

type FindingItem = {
  id: string;
  severity: string;
  status: string;
  title: string;
};

type ReportItem = {
  id: string;
  title: string;
  summary: string;
  createdAt: string;
  artifactPath: string;
  content: string;
  scope: "session" | "project";
  validationWarnings: string[];
};

type ConnectionState =
  | {state: "checking"}
  | {state: "login"; authEnabled: boolean; error: string | null}
  | {state: "ready"; authEnabled: boolean; username: string | null};

type ToolConfigForm = Record<ToolStatusDto["name"], {
  binary_path: string;
  timeout_seconds: string;
  extra_args: string;
  default_wordlist: string;
  templates_path: string;
}>;

const promptSuggestions = [
  "枚举这台靶机的初始攻击面",
  "基于当前证据生成下一步侦察计划",
  "整理 findings 并给出优先级",
];

export function App() {
  const [backendUrl, setRuntimeBackendUrl] = useState(() => getBackendUrl());
  const [connection, setConnection] = useState<ConnectionState>({state: "checking"});
  const [loginDraft, setLoginDraft] = useState({backendUrl: getBackendUrl(), username: "admin", password: ""});
  const [toolStatuses, setToolStatuses] = useState<ToolStatusDto[]>([]);
  const [toolConfig, setToolConfig] = useState<ToolConfigForm>(() => emptyToolConfigForm());
  const [toolSettingsError, setToolSettingsError] = useState<string | null>(null);
  const [toolSettingsSaving, setToolSettingsSaving] = useState(false);
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [mode, setMode] = useState<WorkspaceMode>("Recon");
  const [projectGroups, setProjectGroups] = useState<ProjectGroup[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [projectReports, setProjectReports] = useState<ReportItem[]>([]);
  const [targets, setTargets] = useState<TargetDto[]>([]);
  const [highlightedRef, setHighlightedRef] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [noteSubmitting, setNoteSubmitting] = useState(false);
  const [agentSubmitting, setAgentSubmitting] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [creationError, setCreationError] = useState<string | null>(null);
  const [creationSubmitting, setCreationSubmitting] = useState(false);
  const [projectDraft, setProjectDraft] = useState({name: "", description: ""});
  const [initialDraft, setInitialDraft] = useState({
    projectName: "",
    description: "",
  });
  const authToken = getApiAuthToken();
  const localBackend = isLocalBackendUrl(backendUrl);

  const activeProject = useMemo(
    () => projectGroups.find((group) => group.project.id === activeProjectId)?.project ?? null,
    [activeProjectId, projectGroups],
  );
  const activeSession = useMemo(
    () => projectGroups.flatMap((group) => group.sessions).find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, projectGroups],
  );
  const activeTargets = useMemo(
    () => targets.filter((target) => target.status === "active"),
    [targets],
  );

  const handleAuthError = useCallback((error: unknown, fallback: string): string => {
    const message = error instanceof Error ? error.message : fallback;
    if (message.includes("401")) {
      setApiAuthToken(null);
      setConnection({state: "login", authEnabled: true, error: "Session expired. Sign in again."});
    }
    return message;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function verifySession() {
      setConnection({state: "checking"});
      try {
        const auth = await getAuthSession(backendUrl);
        if (cancelled) {
          return;
        }
        if (!auth.enabled || auth.authenticated) {
          setConnection({state: "ready", authEnabled: auth.enabled, username: auth.username});
          return;
        }
        setConnection({state: "login", authEnabled: true, error: null});
      } catch (error) {
        if (!cancelled) {
          setConnection({
            state: "login",
            authEnabled: false,
            error: error instanceof Error ? error.message : "Failed to connect to backend.",
          });
        }
      }
    }
    void verifySession();
    return () => {
      cancelled = true;
    };
  }, [backendUrl]);

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const nextBackendUrl = setBackendUrl(loginDraft.backendUrl);
      setRuntimeBackendUrl(nextBackendUrl);
      const session = await getAuthSession(nextBackendUrl);
      if (!session.enabled) {
        setConnection({state: "ready", authEnabled: false, username: null});
        return;
      }
      const response = await login(nextBackendUrl, {
        username: loginDraft.username.trim(),
        password: loginDraft.password,
      });
      setConnection({state: "ready", authEnabled: true, username: response.auth.username});
      setLoginDraft((current) => ({...current, password: ""}));
    } catch (error) {
      setConnection({
        state: "login",
        authEnabled: true,
        error: error instanceof Error ? error.message : "Failed to sign in.",
      });
    }
  };

  const signOut = async () => {
    try {
      await logout(backendUrl);
    } catch {
      setApiAuthToken(null);
    }
    setConnection({state: "login", authEnabled: true, error: null});
  };

  const refreshWorkspace = useCallback(
    async (sessionId: string) => {
      const [evidenceItems, findingItems, reportItems] = await Promise.all([
        listEvidence(backendUrl, sessionId),
        listFindings(backendUrl, sessionId),
        listSessionReports(backendUrl, sessionId),
      ]);
      setEvidence(evidenceItems.map(mapEvidence));
      setFindings(findingItems.map(mapFinding));
      setReports(reportItems.map(mapReport));
      setWorkspaceError(null);
    },
    [backendUrl],
  );

  const refreshProjectReports = useCallback(
    async (projectId: string) => {
      const reportItems = await listProjectReports(backendUrl, projectId);
      setProjectReports(reportItems.map(mapReport));
    },
    [backendUrl],
  );

  const refreshProjectTargets = useCallback(
    async (projectId: string) => {
      const targetItems = await listProjectTargets(backendUrl, projectId);
      setTargets(targetItems);
    },
    [backendUrl],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadWorkspaceSessions() {
      try {
        const projects = await listProjects(backendUrl);
        const nextGroups = await Promise.all(
          projects.map(async (project) => ({
            project,
            sessions: await listProjectSessions(backendUrl, project.id),
          })),
        );
        if (cancelled) {
          return;
        }
        setProjectGroups(nextGroups);
        const nextProjectId = activeProjectId && nextGroups.some((group) => group.project.id === activeProjectId)
          ? activeProjectId
          : nextGroups[0]?.project.id ?? null;
        setActiveProjectId(nextProjectId);
        setActiveSessionId((currentSessionId) => {
          if (currentSessionId && nextGroups.some((group) => group.sessions.some((session) => session.id === currentSessionId))) {
            return currentSessionId;
          }
          return nextGroups.find((group) => group.project.id === nextProjectId)?.sessions[0]?.id ?? null;
        });
        if (!nextGroups.some((group) => group.sessions.length > 0)) {
          setEvidence([]);
          setFindings([]);
          setReports([]);
        }
        if (nextProjectId) {
          void refreshProjectReports(nextProjectId);
          void refreshProjectTargets(nextProjectId);
        }
        setWorkspaceError(null);
      } catch (error) {
        if (!cancelled) {
          setWorkspaceError(handleAuthError(error, "Failed to load sessions."));
        }
      }
    }
    void loadWorkspaceSessions();
    return () => {
      cancelled = true;
    };
  }, [activeProjectId, backendUrl, connection.state, handleAuthError, refreshProjectReports, refreshProjectTargets]);

  useEffect(() => {
    seenEventIdsRef.current = new Set();
    setMessages([]);
    setNoteDraft("");
    if (!activeSessionId) {
      setEvidence([]);
      setFindings([]);
      setReports([]);
      setReportError(null);
      return;
    }
  }, [activeSessionId]);

  useEffect(() => {
    if (!activeProjectId) {
      setProjectReports([]);
      setTargets([]);
      return;
    }
    void refreshProjectReports(activeProjectId);
    void refreshProjectTargets(activeProjectId);
  }, [activeProjectId, refreshProjectReports, refreshProjectTargets]);

  const refreshToolSettings = useCallback(async () => {
    try {
      const [statuses, config] = await Promise.all([
        listToolStatus(backendUrl),
        getToolConfig(backendUrl),
      ]);
      setToolStatuses(statuses);
      setToolConfig(toolConfigToForm(config));
      setToolSettingsError(null);
    } catch (error) {
      setToolSettingsError(handleAuthError(error, "Failed to load tool settings."));
    }
  }, [backendUrl, handleAuthError]);

  useEffect(() => {
    if (connection.state !== "ready") {
      return;
    }
    void refreshToolSettings();
  }, [connection.state, refreshToolSettings]);

  useEffect(() => {
    if (!activeSession || connection.state !== "ready") {
      return;
    }
    const sessionId = activeSession.id;
    let cancelled = false;
    async function loadWorkspace() {
      try {
        await refreshWorkspace(sessionId);
      } catch (error) {
        if (!cancelled) {
          setWorkspaceError(handleAuthError(error, "Failed to load workspace."));
        }
      }
    }
    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, [activeSession, connection.state, handleAuthError, refreshWorkspace]);

  const selectProject = (projectId: string) => {
    const group = projectGroups.find((item) => item.project.id === projectId);
    setActiveProjectId(projectId);
    setActiveSessionId(group?.sessions[0]?.id ?? null);
  };

  const selectSession = (projectId: string, sessionId: string) => {
    setActiveProjectId(projectId);
    setActiveSessionId(sessionId);
  };

  const createInitialWorkspace = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const projectError = validateProjectForm({name: initialDraft.projectName});
    if (projectError || creationSubmitting) {
      setCreationError(projectError);
      return;
    }
    setCreationSubmitting(true);
    try {
      const project = await createProject(backendUrl, {
        name: initialDraft.projectName.trim(),
        description: initialDraft.description.trim() || null,
      });
      const session = await createTargetSession(backendUrl, project.id);
      setProjectGroups([{project, sessions: [session]}]);
      await refreshProjectTargets(project.id);
      setActiveProjectId(project.id);
      setActiveSessionId(session.id);
      setInitialDraft({projectName: "", description: ""});
      setCreationError(null);
    } catch (error) {
      setCreationError(error instanceof Error ? error.message : "Failed to initialize workspace.");
    } finally {
      setCreationSubmitting(false);
    }
  };

  const createProjectOnly = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const projectError = validateProjectForm({name: projectDraft.name});
    if (projectError || creationSubmitting) {
      setCreationError(projectError);
      return;
    }
    setCreationSubmitting(true);
    try {
      const project = await createProject(backendUrl, {
        name: projectDraft.name.trim(),
        description: projectDraft.description.trim() || null,
      });
      setProjectGroups((current) => [...current, {project, sessions: []}]);
      setActiveProjectId(project.id);
      setActiveSessionId(null);
      setProjectDraft({name: "", description: ""});
      setNewProjectOpen(false);
      setCreationError(null);
    } catch (error) {
      setCreationError(error instanceof Error ? error.message : "Failed to create project.");
    } finally {
      setCreationSubmitting(false);
    }
  };

  const createSessionForProject = async (projectId: string) => {
    if (creationSubmitting) {
      return;
    }
    setCreationSubmitting(true);
    try {
      const session = await createTargetSession(backendUrl, projectId);
      setProjectGroups((current) =>
        current.map((group) => (
          group.project.id === projectId ? {...group, sessions: [...group.sessions, session]} : group
        )),
      );
      await refreshProjectTargets(projectId);
      setActiveProjectId(projectId);
      setActiveSessionId(session.id);
      setCreationError(null);
    } catch (error) {
      setCreationError(error instanceof Error ? error.message : "Failed to create session.");
    } finally {
      setCreationSubmitting(false);
    }
  };

  const applyFirstMessageTitle = useCallback((sessionId: string, message: string) => {
    const title = titleFromMessage(message);
    if (!title) {
      return;
    }
    setProjectGroups((current) =>
      current.map((group) => ({
        ...group,
        sessions: group.sessions.map((session) => (
          session.id === sessionId && isAutoSessionTitle(session)
            ? {...session, name: title, updated_at: new Date().toISOString()}
            : session
        )),
      })),
    );
  }, []);

  const sendMessage = async (body: string) => {
    const normalized = body.trim();
    const validationError = validateAgentMessageForm({message: normalized});
    if (validationError) {
      setAgentError(validationError);
      return;
    }
    if (!activeSession || agentSubmitting) {
      setAgentError("Select a Session before sending an Agent message.");
      return;
    }
    setAgentSubmitting(true);
    try {
      await sendAgentMessage(backendUrl, activeSession.id, {message: normalized});
      applyFirstMessageTitle(activeSession.id, normalized);
      setDraft("");
      setAgentError(null);
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : "Failed to send Agent message.");
    } finally {
      setAgentSubmitting(false);
    }
  };

  const createManualNote = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = noteDraft.trim();
    if (!normalized || !activeSession || noteSubmitting) {
      return;
    }
    setNoteSubmitting(true);
    try {
      await createEvidence(backendUrl, activeSession.id, {
        evidence_type: "note",
        title: normalized,
        summary: "Manual operator note.",
      });
      setNoteDraft("");
      await refreshWorkspace(activeSession.id);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to create evidence.");
    } finally {
      setNoteSubmitting(false);
    }
  };

  const generateReport = async () => {
    if (!activeSession || reportGenerating) {
      return;
    }
    setReportGenerating(true);
    try {
      const report = await createSessionReport(backendUrl, activeSession.id);
      setReports((current) => [mapReport(report), ...current.filter((item) => item.id !== report.public_id)]);
      setReportError(null);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Failed to generate report.");
    } finally {
      setReportGenerating(false);
    }
  };

  const generateProjectReport = async () => {
    if (!activeProject || reportGenerating) {
      return;
    }
    setReportGenerating(true);
    try {
      const report = await createProjectReport(backendUrl, activeProject.id);
      setProjectReports((current) => [mapReport(report), ...current.filter((item) => item.id !== report.public_id)]);
      setReportError(null);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Failed to generate project report.");
    } finally {
      setReportGenerating(false);
    }
  };

  const openReportFile = async (artifactPath: string) => {
    try {
      await invoke("open_report_path", {path: artifactPath});
      setReportError(null);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : String(error));
    }
  };

  const downloadReportFile = async (reportId: string) => {
    try {
      const headers = authToken ? {Authorization: `Bearer ${authToken}`} : undefined;
      const response = await fetch(reportDownloadUrl(backendUrl, reportId), {headers});
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `${reportId}.md`;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
      setReportError(null);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Failed to download report.");
    }
  };

  const navigateReportReference = (publicId: string) => {
    setHighlightedRef(publicId);
    setMode(publicId.startsWith("CMD") ? "Exploit" : "Recon");
  };

  useEffect(() => {
    if (!activeSession) {
      return;
    }
    const sessionId = activeSession.id;
    const socket = connectEventSocket(
      backendHttpToWebSocketUrl(backendUrl, {sessionId, authToken, replay: true, replayLimit: 60}),
      {
        onStatusChange: () => undefined,
        onEvent: (event) => {
          if (event.session_id && event.session_id !== sessionId) {
            return;
          }
          if (seenEventIdsRef.current.has(event.event_id)) {
            return;
          }
          seenEventIdsRef.current.add(event.event_id);
          if (event.event_kind === "agent.message.received") {
            const message = stringPayload(event.payload.message);
            if (message) {
              applyFirstMessageTitle(sessionId, message);
            }
          }
          const message = mapServerEventToChatMessage(event);
          if (message) {
            setMessages((current) => appendChatMessage(current, message));
          }
          if (
            event.event_kind === "task.completed" ||
            event.event_kind === "task.failed" ||
            event.event_kind === "task.cancelled" ||
            event.event_kind === "agent.workflow.completed" ||
            event.event_kind === "agent.workflow.failed" ||
            event.event_kind === "report.generated"
          ) {
            void refreshWorkspace(sessionId);
            if (activeProjectId) {
              void refreshProjectReports(activeProjectId);
            }
          }
        },
        onError: (message) => setWorkspaceError(message),
      },
    );
    return () => {
      socket.close();
    };
  }, [activeProjectId, activeSession, applyFirstMessageTitle, authToken, backendUrl, refreshProjectReports, refreshWorkspace]);

  const saveToolSettings = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (toolSettingsSaving) {
      return;
    }
    setToolSettingsSaving(true);
    try {
      await updateToolConfig(backendUrl, toolConfigFromForm(toolConfig));
      await refreshToolSettings();
      setToolSettingsError(null);
    } catch (error) {
      setToolSettingsError(handleAuthError(error, "Failed to save tool settings."));
    } finally {
      setToolSettingsSaving(false);
    }
  };

  if (connection.state !== "ready") {
    return (
      <ConnectionPanel
        draft={loginDraft}
        state={connection}
        onDraftChange={setLoginDraft}
        onSubmit={submitLogin}
      />
    );
  }

  return (
    <ErrorBoundary>
    <main className={`immersion-shell ${sidebarOpen ? "sidebar-expanded" : "sidebar-collapsed"}`}>
      <aside className="conversation-rail" aria-label="Conversation management">
        <ConversationPanel
          activeProjectId={activeProjectId}
          activeSessionId={activeSessionId}
          projectGroups={projectGroups}
          collapsed={!sidebarOpen}
          newProjectOpen={newProjectOpen}
          projectDraft={projectDraft}
          creationError={creationError}
          creationSubmitting={creationSubmitting}
          onSelectProject={selectProject}
          onSelectSession={selectSession}
          onToggleNewProject={() => {
            setNewProjectOpen((current) => !current);
            setCreationError(null);
          }}
          onProjectDraftChange={setProjectDraft}
          onCreateProject={createProjectOnly}
          onCreateSession={createSessionForProject}
          onCloseMobile={() => setMobileDrawerOpen(false)}
        />
      </aside>

      <div className={`mobile-drawer ${mobileDrawerOpen ? "open" : ""}`} aria-hidden={!mobileDrawerOpen}>
        <div className="mobile-drawer-surface">
          <ConversationPanel
            activeProjectId={activeProjectId}
            activeSessionId={activeSessionId}
            projectGroups={projectGroups}
            collapsed={false}
            newProjectOpen={newProjectOpen}
            projectDraft={projectDraft}
            creationError={creationError}
            creationSubmitting={creationSubmitting}
            onSelectProject={selectProject}
            onSelectSession={selectSession}
            onToggleNewProject={() => {
              setNewProjectOpen((current) => !current);
              setCreationError(null);
            }}
            onProjectDraftChange={setProjectDraft}
            onCreateProject={createProjectOnly}
            onCreateSession={createSessionForProject}
            onCloseMobile={() => setMobileDrawerOpen(false)}
          />
        </div>
      </div>

      <section className="agent-workspace" aria-label="Agent workspace">
        <header className="agent-header">
          <div className="header-left">
            <button
              type="button"
              className="icon-button mobile-only"
              onClick={() => setMobileDrawerOpen(true)}
              aria-label="Open conversations"
              title="Open conversations"
            >
              <Menu aria-hidden="true" size={20} />
            </button>
            <button
              type="button"
              className="icon-button desktop-only"
              onClick={() => setSidebarOpen((current) => !current)}
              aria-label={sidebarOpen ? "Collapse conversations" : "Expand conversations"}
              title={sidebarOpen ? "Collapse conversations" : "Expand conversations"}
            >
              {sidebarOpen ? <PanelLeftClose aria-hidden="true" size={19} /> : <PanelLeftOpen aria-hidden="true" size={19} />}
            </button>
            <div className="session-heading">
              <span className="session-kicker">
                <Radio aria-hidden="true" size={14} />
                {activeProject?.name ?? "Control Center"}
              </span>
              <h1>{activeSession ? sessionTitle(activeSession) : activeProject ? "Start an Agent Session" : "Initialize workspace"}</h1>
            </div>
          </div>
          <div className="mode-tabs" aria-label="Workspace mode">
            {(["Recon", "Exploit", "Report", "Settings"] as WorkspaceMode[]).map((item) => (
              <button type="button" className={item === mode ? "active" : ""} key={item} onClick={() => setMode(item)}>
                {item}
              </button>
            ))}
          </div>
          <div className="header-status" aria-label="Session status">
            <span>
              <Target aria-hidden="true" size={15} />
              {activeTargets.length} active targets
            </span>
            <span>
              <ShieldCheck aria-hidden="true" size={15} />
              {connection.authEnabled ? connection.username ?? "Signed in" : activeSession?.status ?? "Local"}
            </span>
            {connection.authEnabled ? (
              <button type="button" className="mini-icon-button" onClick={signOut} aria-label="Sign out" title="Sign out">
                <X aria-hidden="true" size={15} />
              </button>
            ) : null}
          </div>
        </header>

        <div className="workspace-grid">
          <section className="conversation-column" aria-label="Agent conversation">
            <section className="conversation-stage">
              <div className="stage-scroll">
                <div className="conversation-body">
                  {!projectGroups.length ? (
                    <InitializationPanel
                      draft={initialDraft}
                      error={creationError}
                      submitting={creationSubmitting}
                      onDraftChange={setInitialDraft}
                      onSubmit={createInitialWorkspace}
                    />
                  ) : activeProject && !activeSession ? (
                    <SessionStartPanel
                      project={activeProject}
                      error={creationError}
                      submitting={creationSubmitting}
                      onCreateSession={() => void createSessionForProject(activeProject.id)}
                    />
                  ) : messages.length ? (
                    messages.map((message) => (
                      <MessageBubble message={message} key={message.id} />
                    ))
                  ) : (
                    <AgentEmptyState session={activeSession} />
                  )}
                </div>
              </div>
              <div className="body-fade" aria-hidden="true" />
            </section>

            <footer className="sender-dock">
              <div className="quick-prompts" aria-label="Prompt suggestions">
                {promptSuggestions.map((prompt) => (
                  <button type="button" key={prompt} disabled={!activeSession || agentSubmitting} onClick={() => void sendMessage(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendMessage(draft);
                }}
              >
                <label htmlFor="agent-draft">Agent prompt</label>
                <textarea
                  id="agent-draft"
                  rows={1}
                  value={draft}
                  disabled={!activeSession || agentSubmitting}
                  placeholder="Ask the Agent to reason about the target..."
                  onChange={(event) => setDraft(event.target.value)}
                />
                <button type="submit" className="send-button" disabled={!activeSession || agentSubmitting} aria-label="Send message" title="Send message">
                  <SendHorizontal aria-hidden="true" size={19} />
                </button>
              </form>
              {agentError ? <p>{agentError}</p> : null}
            </footer>
          </section>

          <IntelPanel
            mode={mode}
            evidence={evidence}
            findings={findings}
            reports={reports}
            projectReports={projectReports}
            highlightedRef={highlightedRef}
            noteDraft={noteDraft}
            workspaceError={workspaceError}
            reportError={reportError}
            reportDisabled={!activeSession || reportGenerating}
            projectReportDisabled={!activeProject || reportGenerating}
            backendUrl={backendUrl}
            localBackend={localBackend}
            toolStatuses={toolStatuses}
            toolConfig={toolConfig}
            toolSettingsError={toolSettingsError}
            toolSettingsSaving={toolSettingsSaving}
            noteDisabled={!activeSession || noteSubmitting}
            onNoteChange={setNoteDraft}
            onCreateNote={createManualNote}
            onGenerateReport={generateReport}
            onGenerateProjectReport={generateProjectReport}
            onDownloadReport={downloadReportFile}
            onOpenReportFile={openReportFile}
            onReferenceClick={navigateReportReference}
            onToolConfigChange={setToolConfig}
            onSaveToolSettings={saveToolSettings}
            onRefreshToolSettings={refreshToolSettings}
          />
        </div>
      </section>
    </main>
    </ErrorBoundary>
  );
}

class ErrorBoundary extends Component<{children: ReactNode}, {error: string | null}> {
  state: {error: string | null} = {error: null};

  static getDerivedStateFromError(error: Error) {
    return {error: error.message};
  }

  render() {
    if (this.state.error) {
      return (
        <main className="connection-shell">
          <section className="connection-panel">
            <div className="welcome-icon" aria-hidden="true">
              <X size={22} />
            </div>
            <h1>Recover Workspace</h1>
            <p>{this.state.error}</p>
            <button type="button" onClick={() => this.setState({error: null})}>Retry</button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function ConnectionPanel({
  draft,
  state,
  onDraftChange,
  onSubmit,
}: {
  draft: {backendUrl: string; username: string; password: string};
  state: ConnectionState;
  onDraftChange: (draft: {backendUrl: string; username: string; password: string}) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <main className="connection-shell">
      <section className="connection-panel" aria-label="Backend connection">
        <div className="welcome-icon" aria-hidden="true">
          <ShieldCheck size={22} />
        </div>
        <h1>Control Center</h1>
        <form className="setup-form" onSubmit={onSubmit}>
          <label htmlFor="backend-url">Backend URL</label>
          <input
            id="backend-url"
            value={draft.backendUrl}
            placeholder="http://127.0.0.1:8000"
            onChange={(event) => onDraftChange({...draft, backendUrl: event.target.value})}
          />
          <label htmlFor="login-username">Username</label>
          <input
            id="login-username"
            value={draft.username}
            disabled={state.state === "checking"}
            placeholder="admin"
            onChange={(event) => onDraftChange({...draft, username: event.target.value})}
          />
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            value={draft.password}
            disabled={state.state === "checking"}
            placeholder="Password"
            onChange={(event) => onDraftChange({...draft, password: event.target.value})}
          />
          <button type="submit" disabled={state.state === "checking"}>
            {state.state === "checking" ? "Checking" : state.authEnabled ? "Sign In" : "Connect"}
          </button>
          {state.state === "login" && state.error ? <p>{state.error}</p> : null}
        </form>
      </section>
    </main>
  );
}

function mapEvidence(item: EvidenceDto): EvidenceItem {
  return {
    id: item.public_id,
    kind: item.evidence_type,
    title: item.title,
    summary: item.summary ?? item.content_ref ?? "No summary recorded.",
  };
}

function mapFinding(item: FindingDto): FindingItem {
  return {
    id: item.public_id,
    severity: item.severity,
    status: item.status,
    title: item.title,
  };
}

function mapReport(item: ReportDto): ReportItem {
  const validation = typeof item.metadata.validation === "object" && item.metadata.validation !== null
    ? item.metadata.validation as Record<string, unknown>
    : {};
  const warnings = Array.isArray(validation.warnings)
    ? validation.warnings.filter((value): value is string => typeof value === "string")
    : [];
  return {
    id: item.public_id,
    title: item.title,
    summary: item.summary,
    createdAt: item.created_at,
    artifactPath: item.artifact_path,
    content: item.content ?? "",
    scope: item.session_id ? "session" : "project",
    validationWarnings: warnings,
  };
}

function formatCompactTime(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return "-";
  }
  return new Date(timestamp).toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function sessionDisplayId(sessionId: string): string {
  return sessionId.replace(/-/g, "").slice(0, 16).toUpperCase();
}

function sessionTitle(session: TargetSessionDto): string {
  return isAutoSessionTitle(session) ? "New session" : session.name;
}

function isAutoSessionTitle(session: TargetSessionDto): boolean {
  const displayId = sessionDisplayId(session.id);
  return !session.name || session.name === displayId || session.name === `Session ${displayId}` || session.name === "New session";
}

function titleFromMessage(message: string): string {
  const normalized = message.trim().replace(/\s+/g, " ");
  if (!normalized) {
    return "";
  }
  return normalized.length <= 60 ? normalized : `${normalized.slice(0, 57)}...`;
}

function stringPayload(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function emptyToolConfigForm(): ToolConfigForm {
  return {
    nmap: {binary_path: "", timeout_seconds: "300", extra_args: "", default_wordlist: "", templates_path: ""},
    ffuf: {binary_path: "", timeout_seconds: "300", extra_args: "", default_wordlist: "", templates_path: ""},
    nuclei: {binary_path: "", timeout_seconds: "300", extra_args: "", default_wordlist: "", templates_path: ""},
  };
}

function toolConfigToForm(config: ToolConfigDto): ToolConfigForm {
  return {
    nmap: scannerToolConfigToForm(config.tools.nmap),
    ffuf: scannerToolConfigToForm(config.tools.ffuf),
    nuclei: scannerToolConfigToForm(config.tools.nuclei),
  };
}

function scannerToolConfigToForm(config: ToolConfigDto["tools"]["nmap"]): ToolConfigForm["nmap"] {
  return {
    binary_path: config.binary_path ?? "",
    timeout_seconds: String(config.timeout_seconds),
    extra_args: config.extra_args.join(" "),
    default_wordlist: config.default_wordlist ?? "",
    templates_path: config.templates_path ?? "",
  };
}

function toolConfigFromForm(form: ToolConfigForm): ToolConfigDto {
  return {
    tools: {
      nmap: scannerToolConfigFromForm(form.nmap),
      ffuf: scannerToolConfigFromForm(form.ffuf),
      nuclei: scannerToolConfigFromForm(form.nuclei),
    },
  };
}

function scannerToolConfigFromForm(form: ToolConfigForm["nmap"]) {
  const timeout = Number.parseInt(form.timeout_seconds, 10);
  if (!Number.isFinite(timeout) || timeout <= 0) {
    throw new Error("timeout_seconds must be greater than 0.");
  }
  return {
    binary_path: form.binary_path.trim() || null,
    timeout_seconds: timeout,
    templates_path: form.templates_path.trim() || null,
    default_wordlist: form.default_wordlist.trim() || null,
    extra_args: form.extra_args.split(/\s+/).map((item) => item.trim()).filter(Boolean),
  };
}

function ConversationPanel({
  activeProjectId,
  activeSessionId,
  projectGroups,
  collapsed,
  newProjectOpen,
  projectDraft,
  creationError,
  creationSubmitting,
  onSelectProject,
  onSelectSession,
  onToggleNewProject,
  onProjectDraftChange,
  onCreateProject,
  onCreateSession,
  onCloseMobile,
}: {
  activeProjectId: string | null;
  activeSessionId: string | null;
  projectGroups: ProjectGroup[];
  collapsed: boolean;
  newProjectOpen: boolean;
  projectDraft: {name: string; description: string};
  creationError: string | null;
  creationSubmitting: boolean;
  onSelectProject: (projectId: string) => void;
  onSelectSession: (projectId: string, sessionId: string) => void;
  onToggleNewProject: () => void;
  onProjectDraftChange: (draft: {name: string; description: string}) => void;
  onCreateProject: (event: FormEvent<HTMLFormElement>) => void;
  onCreateSession: (projectId: string) => void;
  onCloseMobile: () => void;
}) {
  return (
    <div className={`conversation-panel ${collapsed ? "collapsed" : ""}`}>
      <div className="rail-brand">
        <div className="brand-mark" aria-hidden="true">
          <Bot size={20} />
        </div>
        {!collapsed ? (
          <>
            <div>
              <strong>red-code</strong>
              <span>Control Center</span>
            </div>
            <button
              type="button"
              className="icon-button drawer-close"
              onClick={onCloseMobile}
              aria-label="Close conversations"
              title="Close conversations"
            >
              <X aria-hidden="true" size={18} />
            </button>
          </>
        ) : null}
      </div>

      <div className="rail-actions">
        <button type="button" className="icon-text-action" aria-label="New project" title="New project" onClick={onToggleNewProject}>
          <MessageSquarePlus aria-hidden="true" size={18} />
          {!collapsed ? <span>New Project</span> : null}
        </button>
      </div>
      {!collapsed && newProjectOpen ? (
        <ProjectCreatePanel
          draft={projectDraft}
          error={creationError}
          submitting={creationSubmitting}
          onDraftChange={onProjectDraftChange}
          onSubmit={onCreateProject}
        />
      ) : null}

      {!collapsed ? <p className="rail-section-label">Projects</p> : null}
      <nav className="conversation-list project-list" aria-label="Project and Session list">
        {projectGroups.map((group) => (
          <div className="project-group" key={group.project.id}>
            <div className="project-header-row">
              <button
                type="button"
                className={`project-header ${group.project.id === activeProjectId ? "active" : ""}`}
                title={collapsed ? group.project.name : undefined}
                onClick={() => {
                  onSelectProject(group.project.id);
                  if (!group.sessions.length) {
                    onCloseMobile();
                  }
                }}
              >
                <span className="conversation-icon" aria-hidden="true">
                  <Layers3 size={16} />
                </span>
                {!collapsed ? (
                  <span className="conversation-copy">
                    <strong>{group.project.name}</strong>
                    <small>{group.sessions.length} Sessions</small>
                  </span>
                ) : null}
              </button>
              {!collapsed ? (
                <button
                  type="button"
                  className="mini-icon-button"
                  aria-label={`New Session in ${group.project.name}`}
                  title="New Session"
                  onClick={(event) => {
                    event.stopPropagation();
                    onCreateSession(group.project.id);
                  }}
                  disabled={creationSubmitting}
                >
                  <Plus aria-hidden="true" size={15} />
                </button>
              ) : null}
            </div>
            {group.sessions.map((session) => (
              <button
                type="button"
                className={`conversation-item session-item ${session.id === activeSessionId ? "active" : ""}`}
                key={session.id}
                title={collapsed ? sessionTitle(session) : undefined}
                onClick={() => {
                  onSelectSession(group.project.id, session.id);
                  onCloseMobile();
                }}
              >
                <span className="conversation-icon" aria-hidden="true">
                  <Command size={16} />
                </span>
                {!collapsed ? (
                  <span className="conversation-copy">
                    <strong>{sessionTitle(session)}</strong>
                    <small>{sessionDisplayId(session.id)} · {session.status}</small>
                  </span>
                ) : null}
                {!collapsed ? <span className="conversation-time">{formatCompactTime(session.updated_at)}</span> : null}
              </button>
            ))}
          </div>
        ))}
        {!projectGroups.length ? (
          <div className="conversation-empty">
            {!collapsed ? <span>No projects</span> : null}
          </div>
        ) : null}
      </nav>

      {!collapsed ? (
        <div className="rail-footer">
          <CheckCircle2 aria-hidden="true" size={16} />
          <span>Backend workspace ready</span>
        </div>
      ) : null}
    </div>
  );
}

function ProjectCreatePanel({
  draft,
  error,
  submitting,
  onDraftChange,
  onSubmit,
}: {
  draft: {name: string; description: string};
  error: string | null;
  submitting: boolean;
  onDraftChange: (draft: {name: string; description: string}) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="project-create-panel" onSubmit={onSubmit}>
      <div className="project-create-header">
        <Layers3 aria-hidden="true" size={17} />
        <span>New workspace</span>
      </div>
      <div className="project-create-fields">
        <label htmlFor="new-project-name">Project name</label>
        <input
          id="new-project-name"
          value={draft.name}
          disabled={submitting}
          placeholder="HTB Lab"
          onChange={(event) => onDraftChange({...draft, name: event.target.value})}
        />
        <label htmlFor="new-project-description">Description</label>
        <input
          id="new-project-description"
          value={draft.description}
          disabled={submitting}
          placeholder="Scope, platform, or engagement notes"
          onChange={(event) => onDraftChange({...draft, description: event.target.value})}
        />
      </div>
      <div className="project-create-actions">
        {error ? <p>{error}</p> : <span>Project can be linked to Sessions after creation.</span>}
        <button type="submit" disabled={submitting}>Create</button>
      </div>
    </form>
  );
}

function InitializationPanel({
  draft,
  error,
  submitting,
  onDraftChange,
  onSubmit,
}: {
  draft: {projectName: string; description: string};
  error: string | null;
  submitting: boolean;
  onDraftChange: (draft: {projectName: string; description: string}) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="setup-panel workspace-create-panel" aria-label="Initialize workspace">
      <div className="welcome-icon" aria-hidden="true">
        <Target size={22} />
      </div>
      <div className="workspace-create-heading">
        <span>Workspace setup</span>
        <h2>Initialize Project</h2>
      </div>
      <form className="setup-form" onSubmit={onSubmit}>
        <label htmlFor="initial-project-name">Project name</label>
        <input
          id="initial-project-name"
          value={draft.projectName}
          disabled={submitting}
          placeholder="Project name"
          onChange={(event) => onDraftChange({...draft, projectName: event.target.value})}
        />
        <label htmlFor="initial-description">Description</label>
        <textarea
          id="initial-description"
          value={draft.description}
          disabled={submitting}
          placeholder="Scope, platform, or engagement notes"
          onChange={(event) => onDraftChange({...draft, description: event.target.value})}
        />
        <div className="setup-actions">
          {error ? <p>{error}</p> : <span>Creates the Project and opens a new Agent Session.</span>}
          <button type="submit" disabled={submitting}>Create Project</button>
        </div>
      </form>
    </section>
  );
}

function SessionStartPanel({
  project,
  error,
  submitting,
  onCreateSession,
}: {
  project: ProjectDto;
  error: string | null;
  submitting: boolean;
  onCreateSession: () => void;
}) {
  return (
    <section className="setup-panel session-start-panel" aria-label="Start Agent Session">
      <div className="welcome-icon" aria-hidden="true">
        <Command size={22} />
      </div>
      <h2>{project.name}</h2>
      <p>Start a new Agent conversation context for this Project.</p>
      <button type="button" onClick={onCreateSession} disabled={submitting}>Start Agent Session</button>
      {error ? <p>{error}</p> : null}
    </section>
  );
}

function AgentEmptyState({session}: {session: TargetSessionDto | null}) {
  return (
    <section className="agent-empty" aria-label="Agent event stream">
      <Bot aria-hidden="true" size={22} />
      <strong>{session ? sessionTitle(session) : "No Session selected"}</strong>
      <span>{session ? "Agent replay is connected to this Session." : "Select or create a Session."}</span>
    </section>
  );
}

function IntelPanel({
  mode,
  evidence,
  findings,
  reports,
  projectReports,
  highlightedRef,
  noteDraft,
  workspaceError,
  reportError,
  reportDisabled,
  projectReportDisabled,
  backendUrl,
  localBackend,
  toolStatuses,
  toolConfig,
  toolSettingsError,
  toolSettingsSaving,
  noteDisabled,
  onNoteChange,
  onCreateNote,
  onGenerateReport,
  onGenerateProjectReport,
  onDownloadReport,
  onOpenReportFile,
  onReferenceClick,
  onToolConfigChange,
  onSaveToolSettings,
  onRefreshToolSettings,
}: {
  mode: WorkspaceMode;
  evidence: EvidenceItem[];
  findings: FindingItem[];
  reports: ReportItem[];
  projectReports: ReportItem[];
  highlightedRef: string | null;
  noteDraft: string;
  workspaceError: string | null;
  reportError: string | null;
  reportDisabled: boolean;
  projectReportDisabled: boolean;
  backendUrl: string;
  localBackend: boolean;
  toolStatuses: ToolStatusDto[];
  toolConfig: ToolConfigForm;
  toolSettingsError: string | null;
  toolSettingsSaving: boolean;
  noteDisabled: boolean;
  onNoteChange: (value: string) => void;
  onCreateNote: (event: FormEvent<HTMLFormElement>) => void;
  onGenerateReport: () => void;
  onGenerateProjectReport: () => void;
  onDownloadReport: (reportId: string) => void;
  onOpenReportFile: (artifactPath: string) => void;
  onReferenceClick: (publicId: string) => void;
  onToolConfigChange: (config: ToolConfigForm) => void;
  onSaveToolSettings: (event: FormEvent<HTMLFormElement>) => void;
  onRefreshToolSettings: () => void;
}) {
  if (mode === "Settings") {
    return (
      <ToolSettingsPanel
        statuses={toolStatuses}
        config={toolConfig}
        error={toolSettingsError}
        saving={toolSettingsSaving}
        onConfigChange={onToolConfigChange}
        onSubmit={onSaveToolSettings}
        onRefresh={onRefreshToolSettings}
      />
    );
  }
  if (mode === "Report") {
    return (
      <ReportPanel
        reports={reports}
        projectReports={projectReports}
        error={reportError ?? workspaceError}
        disabled={reportDisabled}
        projectDisabled={projectReportDisabled}
        backendUrl={backendUrl}
        localBackend={localBackend}
        onGenerateReport={onGenerateReport}
        onGenerateProjectReport={onGenerateProjectReport}
        onDownloadReport={onDownloadReport}
        onOpenReportFile={onOpenReportFile}
        onReferenceClick={onReferenceClick}
      />
    );
  }

  return (
    <aside className="intel-panel intel-panel-focused" aria-label="Evidence and findings">
      <section className="intel-section evidence-section">
        <div className="panel-heading">
          <Layers3 aria-hidden="true" size={17} />
          <h2>Evidence</h2>
          <span>{evidence.length}</span>
        </div>
        {workspaceError ? <p className="workspace-error">{workspaceError}</p> : null}
        <form className="note-form" onSubmit={onCreateNote}>
          <label htmlFor="manual-note">Manual evidence</label>
          <input
            id="manual-note"
            value={noteDraft}
            placeholder="Record evidence or a note..."
            disabled={noteDisabled}
            onChange={(event) => onNoteChange(event.target.value)}
          />
          <button type="submit" aria-label="Add manual evidence" title="Add manual evidence" disabled={noteDisabled}>
            <ClipboardList aria-hidden="true" size={17} />
          </button>
        </form>
        <div className="evidence-list">
          {evidence.length ? (
            evidence.map((item) => (
              <article className={item.id === highlightedRef ? "highlighted" : ""} key={item.id}>
                <div>
                  <span>{item.kind}</span>
                  <strong>{item.title}</strong>
                </div>
                <p>{item.summary}</p>
              </article>
            ))
          ) : (
            <div className="panel-empty compact">
              <ClipboardList aria-hidden="true" size={18} />
              <span>No evidence recorded</span>
            </div>
          )}
        </div>
      </section>

      <section className="intel-section findings-section">
        <div className="panel-heading">
          <FileText aria-hidden="true" size={17} />
          <h2>Findings</h2>
          <span>{findings.length}</span>
        </div>
        <div className="finding-list">
          {findings.length ? (
            findings.map((finding) => (
              <article className={finding.id === highlightedRef ? "highlighted" : ""} key={finding.id}>
                <div>
                  <span>{finding.severity}</span>
                  <small>{finding.status}</small>
                </div>
                <strong>{finding.title}</strong>
              </article>
            ))
          ) : (
            <div className="panel-empty compact">
              <FileText aria-hidden="true" size={18} />
              <span>No findings yet</span>
            </div>
          )}
        </div>
      </section>
    </aside>
  );
}

function ToolSettingsPanel({
  statuses,
  config,
  error,
  saving,
  onConfigChange,
  onSubmit,
  onRefresh,
}: {
  statuses: ToolStatusDto[];
  config: ToolConfigForm;
  error: string | null;
  saving: boolean;
  onConfigChange: (config: ToolConfigForm) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRefresh: () => void;
}) {
  return (
    <aside className="intel-panel tool-settings-panel" aria-label="Tool settings">
      <section className="intel-section">
        <div className="panel-heading">
          <Settings aria-hidden="true" size={17} />
          <h2>Tool Diagnostics</h2>
          <button type="button" className="mini-icon-button" onClick={onRefresh} aria-label="Refresh tools" title="Refresh tools">
            <RotateCcw aria-hidden="true" size={15} />
          </button>
        </div>
        <div className="tool-status-list">
          {statuses.map((status) => (
            <article key={status.name}>
              <span className={status.available ? "ok" : "missing"}>{status.available ? "available" : "missing"}</span>
              <strong>{status.name}</strong>
              <small>{status.path ?? "No binary path configured"}</small>
              {status.version ? <p>{status.version}</p> : null}
              {status.error ? <p className="workspace-error">{status.error}</p> : null}
            </article>
          ))}
        </div>
      </section>
      <section className="intel-section">
        <div className="panel-heading">
          <Settings aria-hidden="true" size={17} />
          <h2>Tool Configuration</h2>
          <span>{saving ? "saving" : "editable"}</span>
        </div>
        <form className="tool-config-form" onSubmit={onSubmit}>
          {(["nmap", "ffuf", "nuclei"] as ToolStatusDto["name"][]).map((name) => (
            <fieldset key={name}>
              <legend>{name}</legend>
              <label htmlFor={`${name}-binary`}>Binary path</label>
              <input
                id={`${name}-binary`}
                value={config[name].binary_path}
                disabled={saving}
                onChange={(event) => onConfigChange({...config, [name]: {...config[name], binary_path: event.target.value}})}
              />
              <label htmlFor={`${name}-timeout`}>Timeout seconds</label>
              <input
                id={`${name}-timeout`}
                value={config[name].timeout_seconds}
                disabled={saving}
                inputMode="numeric"
                onChange={(event) => onConfigChange({...config, [name]: {...config[name], timeout_seconds: event.target.value}})}
              />
              <label htmlFor={`${name}-extra`}>Extra args</label>
              <input
                id={`${name}-extra`}
                value={config[name].extra_args}
                disabled={saving}
                placeholder="--rate 20"
                onChange={(event) => onConfigChange({...config, [name]: {...config[name], extra_args: event.target.value}})}
              />
              {name === "ffuf" ? (
                <>
                  <label htmlFor="ffuf-wordlist">Default wordlist</label>
                  <input
                    id="ffuf-wordlist"
                    value={config.ffuf.default_wordlist}
                    disabled={saving}
                    onChange={(event) => onConfigChange({...config, ffuf: {...config.ffuf, default_wordlist: event.target.value}})}
                  />
                </>
              ) : null}
              {name === "nuclei" ? (
                <>
                  <label htmlFor="nuclei-templates">Templates path</label>
                  <input
                    id="nuclei-templates"
                    value={config.nuclei.templates_path}
                    disabled={saving}
                    onChange={(event) => onConfigChange({...config, nuclei: {...config.nuclei, templates_path: event.target.value}})}
                  />
                </>
              ) : null}
            </fieldset>
          ))}
          <button type="submit" disabled={saving}>
            <Save aria-hidden="true" size={15} />
            <span>Save</span>
          </button>
          {error ? <p className="workspace-error">{error}</p> : null}
        </form>
      </section>
    </aside>
  );
}

function ReportPanel({
  reports,
  projectReports,
  error,
  disabled,
  projectDisabled,
  backendUrl,
  localBackend,
  onGenerateReport,
  onGenerateProjectReport,
  onDownloadReport,
  onOpenReportFile,
  onReferenceClick,
}: {
  reports: ReportItem[];
  projectReports: ReportItem[];
  error: string | null;
  disabled: boolean;
  projectDisabled: boolean;
  backendUrl: string;
  localBackend: boolean;
  onGenerateReport: () => void;
  onGenerateProjectReport: () => void;
  onDownloadReport: (reportId: string) => void;
  onOpenReportFile: (artifactPath: string) => void;
  onReferenceClick: (publicId: string) => void;
}) {
  const latest = reports[0] ?? null;
  const latestProject = projectReports[0] ?? null;
  return (
    <aside className="intel-panel report-panel" aria-label="Session writeup">
      <section className="intel-section">
        <div className="panel-heading">
          <FileText aria-hidden="true" size={17} />
          <h2>Session Writeup</h2>
          <span>{reports.length}</span>
        </div>
        <div className="report-actions">
          <button type="button" onClick={onGenerateReport} disabled={disabled}>
            <FileText aria-hidden="true" size={15} />
            <span>{latest ? "Regenerate" : "Generate"}</span>
          </button>
          <button type="button" onClick={onGenerateProjectReport} disabled={projectDisabled}>
            <Layers3 aria-hidden="true" size={15} />
            <span>{latestProject ? "Project Regen" : "Project"}</span>
          </button>
          {latest ? (
            <button type="button" onClick={() => onDownloadReport(latest.id)}>
              <Download aria-hidden="true" size={15} />
              <span>Download</span>
            </button>
          ) : null}
          {latest && localBackend ? (
            <button type="button" onClick={() => onOpenReportFile(latest.artifactPath)}>
              <FileText aria-hidden="true" size={15} />
              <span>Open File</span>
            </button>
          ) : null}
        </div>
        {error ? <p className="workspace-error">{error}</p> : null}
        {latest ? (
          <article className="report-preview">
            <div>
              <strong>{latest.title}</strong>
              <small>{formatCompactTime(latest.createdAt)}</small>
            </div>
            <MarkdownPreview markdown={latest.content || latest.summary} onReferenceClick={onReferenceClick} />
            <ReportWarnings report={latest} />
            <small>{latest.artifactPath}</small>
          </article>
        ) : (
          <div className="panel-empty">
            <FileText aria-hidden="true" size={20} />
            <span>No writeup generated</span>
          </div>
        )}
      </section>
      <section className="intel-section">
        <div className="panel-heading">
          <Layers3 aria-hidden="true" size={17} />
          <h2>Project Reports</h2>
          <span>{projectReports.length}</span>
        </div>
        {latestProject ? (
          <article className="report-preview compact">
            <div>
              <strong>{latestProject.title}</strong>
              <small>{formatCompactTime(latestProject.createdAt)}</small>
            </div>
            <MarkdownPreview markdown={latestProject.content || latestProject.summary} onReferenceClick={onReferenceClick} />
            <ReportWarnings report={latestProject} />
            <div className="report-inline-actions">
              <button type="button" onClick={() => onDownloadReport(latestProject.id)}>Download</button>
              {localBackend ? (
                <button type="button" onClick={() => onOpenReportFile(latestProject.artifactPath)}>Open File</button>
              ) : null}
            </div>
          </article>
        ) : null}
      </section>
      <section className="intel-section">
        <div className="panel-heading">
          <FileText aria-hidden="true" size={17} />
          <h2>Session Reports</h2>
          <span>{reports.length}</span>
        </div>
        <div className="report-list">
          {reports.map((report) => (
            <article key={report.id}>
              <span>{formatCompactTime(report.createdAt)}</span>
              <strong>{report.title}</strong>
              <p>{report.summary}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="intel-section">
        <div className="panel-heading">
          <Layers3 aria-hidden="true" size={17} />
          <h2>Project History</h2>
          <span>{projectReports.length}</span>
        </div>
        <div className="report-list">
          {projectReports.map((report) => (
            <article key={report.id}>
              <span>{formatCompactTime(report.createdAt)}</span>
              <strong>{report.title}</strong>
              <p>{report.summary}</p>
            </article>
          ))}
        </div>
      </section>
    </aside>
  );
}

function MarkdownPreview({markdown, onReferenceClick}: {markdown: string; onReferenceClick: (publicId: string) => void}) {
  const tokens = markdown.split(/(\b(?:P|T|TASK|EVID|FIND|AP|CMD|FLAG|RPT)\d{4}\b)/g);
  return (
    <pre>
      {tokens.map((token, index) => (
        /^(?:P|T|TASK|EVID|FIND|AP|CMD|FLAG|RPT)\d{4}$/.test(token) ? (
          <button type="button" className="report-ref" key={`${token}-${index}`} onClick={() => onReferenceClick(token)}>
            {token}
          </button>
        ) : token
      ))}
    </pre>
  );
}

function ReportWarnings({report}: {report: ReportItem}) {
  if (!report.validationWarnings.length) {
    return null;
  }
  return (
    <div className="report-warnings">
      {report.validationWarnings.map((warning) => <span key={warning}>{warning}</span>)}
    </div>
  );
}

function MessageBubble({message}: { message: ChatMessage }) {
  if (message.role === "system") {
    return (
      <div className="system-line">
        <span>{message.body}</span>
      </div>
    );
  }
  if (message.role === "execution") {
    return (
      <article className={`message-row agent execution-message ${message.executionStatus ?? "running"}`}>
        <div className="message-avatar" aria-hidden="true">
          <Bot size={18} />
        </div>
        <div className="message-content">
          <div className="message-meta">
            <span>{message.title ?? "Execution steps"}</span>
            <small>{message.meta}</small>
          </div>
          <p>{message.body}</p>
          <div className="execution-step-list" aria-label="Agent execution steps">
            {(message.executionSteps ?? []).map((step) => (
              <div className={`execution-step ${step.kind} ${step.status ?? ""}`} key={step.id}>
                <div className="execution-step-marker" aria-hidden="true" />
                <div className="execution-step-copy">
                  <div className="execution-step-header">
                    <span>{stepLabel(step.kind)}</span>
                    <strong>{step.title}</strong>
                    {step.status ? <small>{step.status}</small> : null}
                  </div>
                  <p>{step.body}</p>
                  {step.chips?.length ? (
                    <div className="agent-steps compact" aria-label="Step details">
                      {step.chips.map((chip) => <span key={chip}>{chip}</span>)}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className={`message-row ${message.role}`}>
      <div className="message-avatar" aria-hidden="true">
        {message.role === "agent" ? <Bot size={18} /> : <Target size={18} />}
      </div>
      <div className="message-content">
        <div className="message-meta">
          <span>{message.title ?? (message.role === "operator" ? "Operator" : "Agent")}</span>
          <small>{message.meta}</small>
        </div>
        <p>{message.body}</p>
        {message.steps ? (
          <div className="agent-steps" aria-label="Agent progress">
            {message.steps.map((step) => (
              <span key={step}>{step}</span>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function stepLabel(kind: NonNullable<ChatMessage["executionSteps"]>[number]["kind"]): string {
  switch (kind) {
    case "workflow":
      return "workflow";
    case "thinking":
      return "agent";
    case "tool":
      return "tool";
    case "command":
      return "command";
    case "result":
      return "result";
    case "plan":
      return "plan";
    case "artifact":
      return "artifact";
    default:
      return "event";
  }
}
