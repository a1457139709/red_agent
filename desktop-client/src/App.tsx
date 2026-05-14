import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ClipboardList,
  Command,
  FileText,
  Flag,
  GitBranch,
  Layers3,
  Menu,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Radio,
  Save,
  SendHorizontal,
  ShieldCheck,
  Terminal as TerminalIcon,
  Target,
  X,
} from "lucide-react";
import {
  type AttackPathNodeDto,
  type CommandRunDto,
  type CreateTargetSessionInput,
  type EvidenceDto,
  type FindingDto,
  type FlagDto,
  type ProjectDto,
  type TargetSessionDto,
  type TargetType,
  type TerminalDto,
  createCommandEvidence,
  createEvidence,
  createProject,
  createTargetSession,
  getBackendUrl,
  listTerminalCommands,
  listAttackPath,
  listEvidence,
  listFindings,
  listFlags,
  listProjectSessions,
  listProjects,
  openTerminal,
  sendAgentMessage,
} from "./lib/api";
import { TARGET_TYPE_OPTIONS, validateAgentMessageForm, validateProjectForm, validateTargetSessionForm } from "./lib/forms";
import { type ChatMessage, mapServerEventToChatMessage } from "./lib/agentEvents";
import { type EventSocketController, backendHttpToWebSocketUrl, connectEventSocket } from "./lib/ws";

type WorkspaceMode = "Recon" | "Exploit" | "Report";

type ProjectGroup = {
  project: ProjectDto;
  sessions: TargetSessionDto[];
};

type SessionDraft = {
  name: string;
  target_value: string;
  target_type: TargetType;
  summary: string;
};

type EvidenceItem = {
  id: string;
  kind: string;
  title: string;
  summary: string;
};

type AttackNode = {
  id: string;
  stage: string;
  title: string;
  status: string;
  nextAction: string;
  evidenceIds: string[];
};

type FindingItem = {
  id: string;
  severity: string;
  status: string;
  title: string;
};

type FlagItem = {
  id: string;
  type: string;
  value: string;
  evidenceId: string;
};

type TerminalTab = {
  terminalId: string;
  status: string;
  workingDirectory: string;
  output: string;
  draft: string;
  selection: string;
  commands: CommandRunDto[];
};

const promptSuggestions = [
  "枚举这台靶机的初始攻击面",
  "基于当前证据生成下一步侦察计划",
  "整理 findings 并给出优先级",
];

export function App() {
  const backendUrl = useMemo(() => getBackendUrl(), []);
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
  const [nodes, setNodes] = useState<AttackNode[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [flags, setFlags] = useState<FlagItem[]>([]);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [noteSubmitting, setNoteSubmitting] = useState(false);
  const [agentSubmitting, setAgentSubmitting] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [terminalTabs, setTerminalTabs] = useState<TerminalTab[]>([]);
  const [activeTerminalId, setActiveTerminalId] = useState<string | null>(null);
  const [terminalError, setTerminalError] = useState<string | null>(null);
  const [terminalSocket, setTerminalSocket] = useState<EventSocketController | null>(null);
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [newSessionProjectId, setNewSessionProjectId] = useState<string | null>(null);
  const [creationError, setCreationError] = useState<string | null>(null);
  const [creationSubmitting, setCreationSubmitting] = useState(false);
  const [projectDraft, setProjectDraft] = useState({name: "", description: ""});
  const [sessionDraft, setSessionDraft] = useState<SessionDraft>(emptySessionDraft());
  const [initialDraft, setInitialDraft] = useState({
    projectName: "",
    sessionName: "",
    targetValue: "",
    targetType: "ip" as TargetType,
    summary: "",
  });

  const activeProject = useMemo(
    () => projectGroups.find((group) => group.project.id === activeProjectId)?.project ?? null,
    [activeProjectId, projectGroups],
  );
  const activeSession = useMemo(
    () => projectGroups.flatMap((group) => group.sessions).find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, projectGroups],
  );

  const refreshWorkspace = useCallback(
    async (sessionId: string) => {
      const [attackPathItems, evidenceItems, findingItems, flagItems] = await Promise.all([
        listAttackPath(backendUrl, sessionId),
        listEvidence(backendUrl, sessionId),
        listFindings(backendUrl, sessionId),
        listFlags(backendUrl, sessionId),
      ]);
      const evidenceById = new Map(evidenceItems.map((item) => [item.id, item.public_id]));
      setEvidence(evidenceItems.map(mapEvidence));
      setNodes(attackPathItems.map(mapAttackNode));
      setFindings(findingItems.map(mapFinding));
      setFlags(flagItems.map((flag) => mapFlag(flag, evidenceById)));
      setWorkspaceError(null);
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
        setActiveProjectId((currentProjectId) => {
          const nextProjectId = currentProjectId && nextGroups.some((group) => group.project.id === currentProjectId)
            ? currentProjectId
            : nextGroups[0]?.project.id ?? null;
          setActiveSessionId((currentSessionId) => {
            if (currentSessionId && nextGroups.some((group) => group.sessions.some((session) => session.id === currentSessionId))) {
              return currentSessionId;
            }
            return nextGroups.find((group) => group.project.id === nextProjectId)?.sessions[0]?.id ?? null;
          });
          return nextProjectId;
        });
        if (!nextGroups.some((group) => group.sessions.length > 0)) {
          setEvidence([]);
          setNodes([]);
          setFindings([]);
          setFlags([]);
        }
        setWorkspaceError(null);
      } catch (error) {
        if (!cancelled) {
          setWorkspaceError(error instanceof Error ? error.message : "Failed to load sessions.");
        }
      }
    }
    void loadWorkspaceSessions();
    return () => {
      cancelled = true;
    };
  }, [backendUrl]);

  useEffect(() => {
    seenEventIdsRef.current = new Set();
    setMessages([]);
    setTerminalTabs([]);
    setActiveTerminalId(null);
    setTerminalError(null);
    if (!activeSessionId) {
      setEvidence([]);
      setNodes([]);
      setFindings([]);
      setFlags([]);
      return;
    }
  }, [activeSessionId]);

  useEffect(() => {
    if (!activeSession) {
      return;
    }
    const sessionId = activeSession.id;
    let cancelled = false;
    async function loadWorkspace() {
      try {
        await refreshWorkspace(sessionId);
      } catch (error) {
        if (!cancelled) {
          setWorkspaceError(error instanceof Error ? error.message : "Failed to load workspace.");
        }
      }
    }
    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, [activeSession, refreshWorkspace]);

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
    const sessionError = validateTargetSessionForm({
      name: initialDraft.sessionName,
      target_value: initialDraft.targetValue,
      target_type: initialDraft.targetType,
    });
    if (projectError || sessionError || creationSubmitting) {
      setCreationError(projectError ?? sessionError);
      return;
    }
    setCreationSubmitting(true);
    try {
      const project = await createProject(backendUrl, {
        name: initialDraft.projectName.trim(),
        description: initialDraft.summary.trim() || null,
      });
      const session = await createTargetSession(backendUrl, project.id, {
        name: initialDraft.sessionName.trim(),
        target_value: initialDraft.targetValue.trim(),
        target_type: initialDraft.targetType,
        summary: initialDraft.summary.trim() || null,
      });
      setProjectGroups([{project, sessions: [session]}]);
      setActiveProjectId(project.id);
      setActiveSessionId(session.id);
      setInitialDraft({projectName: "", sessionName: "", targetValue: "", targetType: "ip", summary: ""});
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

  const createSessionForProject = async (event: FormEvent<HTMLFormElement>, projectId: string) => {
    event.preventDefault();
    const sessionError = validateTargetSessionForm(sessionDraft);
    if (sessionError || creationSubmitting) {
      setCreationError(sessionError);
      return;
    }
    setCreationSubmitting(true);
    try {
      const input: CreateTargetSessionInput = {
        name: sessionDraft.name.trim(),
        target_value: sessionDraft.target_value.trim(),
        target_type: sessionDraft.target_type,
        summary: sessionDraft.summary.trim() || null,
      };
      const session = await createTargetSession(backendUrl, projectId, input);
      setProjectGroups((current) =>
        current.map((group) => (
          group.project.id === projectId ? {...group, sessions: [...group.sessions, session]} : group
        )),
      );
      setActiveProjectId(projectId);
      setActiveSessionId(session.id);
      setSessionDraft(emptySessionDraft());
      setNewSessionProjectId(null);
      setCreationError(null);
    } catch (error) {
      setCreationError(error instanceof Error ? error.message : "Failed to create session.");
    } finally {
      setCreationSubmitting(false);
    }
  };

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

  const refreshTerminalCommands = useCallback(
    async (terminalId: string) => {
      try {
        const commands = await listTerminalCommands(backendUrl, terminalId);
        setTerminalTabs((current) =>
          current.map((tab) => (tab.terminalId === terminalId ? {...tab, commands} : tab)),
        );
      } catch (error) {
        setTerminalError(error instanceof Error ? error.message : "Failed to load command history.");
      }
    },
    [backendUrl],
  );

  useEffect(() => {
    if (!activeSession) {
      return;
    }
    const sessionId = activeSession.id;
    const socket = connectEventSocket(
      backendHttpToWebSocketUrl(backendUrl, {sessionId, replay: true, replayLimit: 60}),
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
          if (event.event_kind === "terminal.output") {
            const terminalId = stringPayload(event.payload.terminal_id);
            const chunk = stringPayload(event.payload.chunk);
            if (!terminalId || chunk === null) {
              return;
            }
            setTerminalTabs((current) =>
              current.map((tab) => (
                tab.terminalId === terminalId ? {...tab, output: `${tab.output}${chunk}`} : tab
              )),
            );
          }
          if (event.event_kind === "terminal.exited") {
            const terminalId = stringPayload(event.payload.terminal_id);
            if (!terminalId) {
              return;
            }
            setTerminalTabs((current) =>
              current.map((tab) => (
                tab.terminalId === terminalId ? {...tab, status: "exited"} : tab
              )),
            );
            void refreshTerminalCommands(terminalId);
          }
          if (event.event_kind === "agent.terminal_command.suggested") {
            const command = stringPayload(event.payload.command);
            if (command) {
              setTerminalTabs((current) =>
                current.map((tab) => (
                  tab.terminalId === activeTerminalId ? {...tab, draft: command} : tab
                )),
              );
            }
          }
          const message = mapServerEventToChatMessage(event);
          if (message) {
            setMessages((current) => [...current, message]);
          }
          if (
            event.event_kind === "task.completed" ||
            event.event_kind === "task.failed" ||
            event.event_kind === "task.cancelled" ||
            event.event_kind === "agent.workflow.completed" ||
            event.event_kind === "agent.workflow.failed"
          ) {
            void refreshWorkspace(sessionId);
          }
        },
        onError: (message) => setTerminalError(message),
      },
    );
    setTerminalSocket(socket);
    return () => {
      socket.close();
      setTerminalSocket(null);
    };
  }, [activeSession, activeTerminalId, backendUrl, refreshTerminalCommands, refreshWorkspace]);

  const openTerminalTab = async () => {
    if (!activeSession) {
      return;
    }
    try {
      const terminal = await openTerminal(backendUrl, activeSession.id, {rows: 24, cols: 80});
      const nextTab = mapTerminalTab(terminal);
      setTerminalTabs((current) => [...current, nextTab]);
      setActiveTerminalId(nextTab.terminalId);
      setTerminalError(null);
    } catch (error) {
      setTerminalError(error instanceof Error ? error.message : "Failed to open terminal.");
    }
  };

  const sendTerminalInput = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const activeTab = terminalTabs.find((tab) => tab.terminalId === activeTerminalId);
    if (!activeTab || !activeTab.draft.trim() || !terminalSocket) {
      return;
    }
    const data = `${activeTab.draft}\n`;
    const sent = terminalSocket.send("terminal.input", {terminal_id: activeTab.terminalId, data});
    if (!sent) {
      setTerminalError("Terminal WebSocket is not connected.");
      return;
    }
    setTerminalTabs((current) =>
      current.map((tab) => (tab.terminalId === activeTab.terminalId ? {...tab, draft: ""} : tab)),
    );
    window.setTimeout(() => {
      void refreshTerminalCommands(activeTab.terminalId);
    }, 250);
  };

  const closeActiveTerminal = () => {
    if (!activeTerminalId || !terminalSocket) {
      return;
    }
    terminalSocket.send("terminal.close", {terminal_id: activeTerminalId});
  };

  const saveTerminalSelection = async () => {
    const activeTab = terminalTabs.find((tab) => tab.terminalId === activeTerminalId);
    const command = activeTab?.commands[0];
    if (!activeTab || !command || !activeTab.selection.trim()) {
      return;
    }
    try {
      await createCommandEvidence(backendUrl, command.id, {
        title: `Terminal output: ${command.command}`,
        selected_text: activeTab.selection,
        tags: ["terminal"],
      });
      await refreshWorkspace(activeTab.commands[0].session_id);
      setTerminalTabs((current) =>
        current.map((tab) => (tab.terminalId === activeTab.terminalId ? {...tab, selection: ""} : tab)),
      );
    } catch (error) {
      setTerminalError(error instanceof Error ? error.message : "Failed to save terminal evidence.");
    }
  };

  return (
    <main className={`immersion-shell ${sidebarOpen ? "sidebar-expanded" : "sidebar-collapsed"}`}>
      <aside className="conversation-rail" aria-label="Conversation management">
        <ConversationPanel
          activeProjectId={activeProjectId}
          activeSessionId={activeSessionId}
          projectGroups={projectGroups}
          collapsed={!sidebarOpen}
          newProjectOpen={newProjectOpen}
          newSessionProjectId={newSessionProjectId}
          projectDraft={projectDraft}
          sessionDraft={sessionDraft}
          creationError={creationError}
          creationSubmitting={creationSubmitting}
          onSelectProject={selectProject}
          onSelectSession={selectSession}
          onToggleNewProject={() => {
            setNewProjectOpen((current) => !current);
            setNewSessionProjectId(null);
            setCreationError(null);
          }}
          onToggleNewSession={(projectId) => {
            setNewSessionProjectId((current) => (current === projectId ? null : projectId));
            setNewProjectOpen(false);
            setCreationError(null);
          }}
          onProjectDraftChange={setProjectDraft}
          onSessionDraftChange={setSessionDraft}
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
            newSessionProjectId={newSessionProjectId}
            projectDraft={projectDraft}
            sessionDraft={sessionDraft}
            creationError={creationError}
            creationSubmitting={creationSubmitting}
            onSelectProject={selectProject}
            onSelectSession={selectSession}
            onToggleNewProject={() => {
              setNewProjectOpen((current) => !current);
              setNewSessionProjectId(null);
              setCreationError(null);
            }}
            onToggleNewSession={(projectId) => {
              setNewSessionProjectId((current) => (current === projectId ? null : projectId));
              setNewProjectOpen(false);
              setCreationError(null);
            }}
            onProjectDraftChange={setProjectDraft}
            onSessionDraftChange={setSessionDraft}
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
              <h1>{activeSession?.name ?? (activeProject ? "Create a Session" : "Initialize workspace")}</h1>
            </div>
          </div>
          <div className="mode-tabs" aria-label="Workspace mode">
            {(["Recon", "Exploit", "Report"] as WorkspaceMode[]).map((item) => (
              <button type="button" className={item === mode ? "active" : ""} key={item} onClick={() => setMode(item)}>
                {item}
              </button>
            ))}
          </div>
          <div className="header-status" aria-label="Session status">
            <span>
              <Target aria-hidden="true" size={15} />
              {activeSession?.target_value ?? "No target"}
            </span>
            <span>
              <ShieldCheck aria-hidden="true" size={15} />
              {activeSession?.target_type ?? "Project"}
            </span>
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
                    <SessionSetupPanel
                      project={activeProject}
                      draft={sessionDraft}
                      error={creationError}
                      submitting={creationSubmitting}
                      onDraftChange={setSessionDraft}
                      onSubmit={(event) => createSessionForProject(event, activeProject.id)}
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
            nodes={nodes}
            evidence={evidence}
            findings={findings}
            flags={flags}
            noteDraft={noteDraft}
            workspaceError={workspaceError}
            noteDisabled={!activeSession || noteSubmitting}
            onNoteChange={setNoteDraft}
            onCreateNote={createManualNote}
          />
          <TerminalPanel
            tabs={terminalTabs}
            activeTerminalId={activeTerminalId}
            error={terminalError}
            disabled={!activeSession}
            onOpenTerminal={openTerminalTab}
            onSelectTerminal={setActiveTerminalId}
            onCloseTerminal={closeActiveTerminal}
            onDraftChange={(terminalId, draftValue) => {
              setTerminalTabs((current) =>
                current.map((tab) => (tab.terminalId === terminalId ? {...tab, draft: draftValue} : tab)),
              );
            }}
            onSelectionChange={(terminalId, selection) => {
              setTerminalTabs((current) =>
                current.map((tab) => (tab.terminalId === terminalId ? {...tab, selection} : tab)),
              );
            }}
            onSubmit={sendTerminalInput}
            onSaveSelection={saveTerminalSelection}
          />
        </div>
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

function mapAttackNode(item: AttackPathNodeDto): AttackNode {
  return {
    id: item.public_id,
    stage: item.stage,
    title: item.title,
    status: item.status,
    nextAction: item.next_action ?? "Review linked evidence.",
    evidenceIds: item.evidence.map((evidenceItem) => evidenceItem.public_id),
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

function mapFlag(item: FlagDto, evidenceById: Map<string, string>): FlagItem {
  return {
    id: item.public_id,
    type: item.flag_type,
    value: item.value,
    evidenceId: item.source_evidence_id ? evidenceById.get(item.source_evidence_id) ?? item.source_evidence_id : "-",
  };
}

function mapTerminalTab(item: TerminalDto): TerminalTab {
  return {
    terminalId: item.terminal_id,
    status: item.status,
    workingDirectory: item.working_directory,
    output: "",
    draft: "",
    selection: "",
    commands: [],
  };
}

function stringPayload(value: unknown): string | null {
  return typeof value === "string" ? value : null;
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

function emptySessionDraft(): SessionDraft {
  return {name: "", target_value: "", target_type: "ip", summary: ""};
}

function ConversationPanel({
  activeProjectId,
  activeSessionId,
  projectGroups,
  collapsed,
  newProjectOpen,
  newSessionProjectId,
  projectDraft,
  sessionDraft,
  creationError,
  creationSubmitting,
  onSelectProject,
  onSelectSession,
  onToggleNewProject,
  onToggleNewSession,
  onProjectDraftChange,
  onSessionDraftChange,
  onCreateProject,
  onCreateSession,
  onCloseMobile,
}: {
  activeProjectId: string | null;
  activeSessionId: string | null;
  projectGroups: ProjectGroup[];
  collapsed: boolean;
  newProjectOpen: boolean;
  newSessionProjectId: string | null;
  projectDraft: {name: string; description: string};
  sessionDraft: SessionDraft;
  creationError: string | null;
  creationSubmitting: boolean;
  onSelectProject: (projectId: string) => void;
  onSelectSession: (projectId: string, sessionId: string) => void;
  onToggleNewProject: () => void;
  onToggleNewSession: (projectId: string) => void;
  onProjectDraftChange: (draft: {name: string; description: string}) => void;
  onSessionDraftChange: (draft: SessionDraft) => void;
  onCreateProject: (event: FormEvent<HTMLFormElement>) => void;
  onCreateSession: (event: FormEvent<HTMLFormElement>, projectId: string) => void;
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
        <form className="rail-create-form" onSubmit={onCreateProject}>
          <label htmlFor="new-project-name">Project name</label>
          <input
            id="new-project-name"
            value={projectDraft.name}
            disabled={creationSubmitting}
            placeholder="Project name"
            onChange={(event) => onProjectDraftChange({...projectDraft, name: event.target.value})}
          />
          <input
            value={projectDraft.description}
            disabled={creationSubmitting}
            placeholder="Description"
            onChange={(event) => onProjectDraftChange({...projectDraft, description: event.target.value})}
          />
          <button type="submit" disabled={creationSubmitting}>Create Project</button>
          {creationError ? <p>{creationError}</p> : null}
        </form>
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
                    onToggleNewSession(group.project.id);
                  }}
                >
                  <Plus aria-hidden="true" size={15} />
                </button>
              ) : null}
            </div>
            {!collapsed && newSessionProjectId === group.project.id ? (
              <SessionMiniForm
                draft={sessionDraft}
                error={creationError}
                submitting={creationSubmitting}
                onDraftChange={onSessionDraftChange}
                onSubmit={(event) => onCreateSession(event, group.project.id)}
              />
            ) : null}
            {group.sessions.map((session) => (
              <button
                type="button"
                className={`conversation-item session-item ${session.id === activeSessionId ? "active" : ""}`}
                key={session.id}
                title={collapsed ? session.name : undefined}
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
                    <strong>{session.name}</strong>
                    <small>{session.target_type} · {session.target_value}</small>
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

function InitializationPanel({
  draft,
  error,
  submitting,
  onDraftChange,
  onSubmit,
}: {
  draft: {projectName: string; sessionName: string; targetValue: string; targetType: TargetType; summary: string};
  error: string | null;
  submitting: boolean;
  onDraftChange: (draft: {projectName: string; sessionName: string; targetValue: string; targetType: TargetType; summary: string}) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="setup-panel" aria-label="Initialize workspace">
      <div className="welcome-icon" aria-hidden="true">
        <Target size={22} />
      </div>
      <h2>Initialize Project</h2>
      <form className="setup-form" onSubmit={onSubmit}>
        <label htmlFor="initial-project-name">Project name</label>
        <input
          id="initial-project-name"
          value={draft.projectName}
          disabled={submitting}
          placeholder="Project name"
          onChange={(event) => onDraftChange({...draft, projectName: event.target.value})}
        />
        <label htmlFor="initial-session-name">Session name</label>
        <input
          id="initial-session-name"
          value={draft.sessionName}
          disabled={submitting}
          placeholder="Session name"
          onChange={(event) => onDraftChange({...draft, sessionName: event.target.value})}
        />
        <div className="setup-row">
          <label htmlFor="initial-target-type">Target type</label>
          <select
            id="initial-target-type"
            value={draft.targetType}
            disabled={submitting}
            onChange={(event) => onDraftChange({...draft, targetType: event.target.value as TargetType})}
          >
            {TARGET_TYPE_OPTIONS.map((option) => <option value={option} key={option}>{option}</option>)}
          </select>
          <label htmlFor="initial-target-value">Target value</label>
          <input
            id="initial-target-value"
            value={draft.targetValue}
            disabled={submitting}
            placeholder="10.10.10.5"
            onChange={(event) => onDraftChange({...draft, targetValue: event.target.value})}
          />
        </div>
        <label htmlFor="initial-summary">Summary</label>
        <textarea
          id="initial-summary"
          value={draft.summary}
          disabled={submitting}
          placeholder="Scope notes"
          onChange={(event) => onDraftChange({...draft, summary: event.target.value})}
        />
        <button type="submit" disabled={submitting}>Create Project and Session</button>
        {error ? <p>{error}</p> : null}
      </form>
    </section>
  );
}

function SessionSetupPanel({
  project,
  draft,
  error,
  submitting,
  onDraftChange,
  onSubmit,
}: {
  project: ProjectDto;
  draft: SessionDraft;
  error: string | null;
  submitting: boolean;
  onDraftChange: (draft: SessionDraft) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="setup-panel" aria-label="Create Session">
      <div className="welcome-icon" aria-hidden="true">
        <Command size={22} />
      </div>
      <h2>{project.name}</h2>
      <SessionMiniForm
        draft={draft}
        error={error}
        submitting={submitting}
        onDraftChange={onDraftChange}
        onSubmit={onSubmit}
        submitLabel="Create Session"
        expanded
      />
    </section>
  );
}

function AgentEmptyState({session}: {session: TargetSessionDto | null}) {
  return (
    <section className="agent-empty" aria-label="Agent event stream">
      <Bot aria-hidden="true" size={22} />
      <strong>{session ? session.name : "No Session selected"}</strong>
      <span>{session ? "Agent replay is connected to this Session." : "Select or create a Session."}</span>
    </section>
  );
}

function SessionMiniForm({
  draft,
  error,
  submitting,
  onDraftChange,
  onSubmit,
  submitLabel = "Create",
  expanded = false,
}: {
  draft: SessionDraft;
  error: string | null;
  submitting: boolean;
  onDraftChange: (draft: SessionDraft) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  submitLabel?: string;
  expanded?: boolean;
}) {
  return (
    <form className={`rail-create-form session-create-form ${expanded ? "expanded" : ""}`} onSubmit={onSubmit}>
      <label htmlFor={expanded ? "setup-session-name" : "rail-session-name"}>Session name</label>
      <input
        id={expanded ? "setup-session-name" : "rail-session-name"}
        value={draft.name}
        disabled={submitting}
        placeholder="Session name"
        onChange={(event) => onDraftChange({...draft, name: event.target.value})}
      />
      <div className="setup-row">
        <label htmlFor={expanded ? "setup-target-type" : "rail-target-type"}>Target type</label>
        <select
          id={expanded ? "setup-target-type" : "rail-target-type"}
          value={draft.target_type}
          disabled={submitting}
          onChange={(event) => onDraftChange({...draft, target_type: event.target.value as TargetType})}
        >
          {TARGET_TYPE_OPTIONS.map((option) => <option value={option} key={option}>{option}</option>)}
        </select>
        <label htmlFor={expanded ? "setup-target-value" : "rail-target-value"}>Target value</label>
        <input
          id={expanded ? "setup-target-value" : "rail-target-value"}
          value={draft.target_value}
          disabled={submitting}
          placeholder="Target"
          onChange={(event) => onDraftChange({...draft, target_value: event.target.value})}
        />
      </div>
      <textarea
        value={draft.summary}
        disabled={submitting}
        placeholder="Summary"
        onChange={(event) => onDraftChange({...draft, summary: event.target.value})}
      />
      <button type="submit" disabled={submitting}>{submitLabel}</button>
      {error ? <p>{error}</p> : null}
    </form>
  );
}

function IntelPanel({
  mode,
  nodes,
  evidence,
  findings,
  flags,
  noteDraft,
  workspaceError,
  noteDisabled,
  onNoteChange,
  onCreateNote,
}: {
  mode: WorkspaceMode;
  nodes: AttackNode[];
  evidence: EvidenceItem[];
  findings: FindingItem[];
  flags: FlagItem[];
  noteDraft: string;
  workspaceError: string | null;
  noteDisabled: boolean;
  onNoteChange: (value: string) => void;
  onCreateNote: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <aside className="intel-panel" aria-label="Attack path and evidence">
      <section className="intel-section">
        <div className="panel-heading">
          <GitBranch aria-hidden="true" size={17} />
          <h2>Attack Path</h2>
          <span>{mode}</span>
        </div>
        <div className="attack-board">
          {nodes.map((node) => (
            <article className={`attack-node ${node.status}`} key={node.id}>
              <div>
                <span>{node.stage}</span>
                <strong>{node.title}</strong>
              </div>
              <p>{node.nextAction}</p>
              <small>{node.evidenceIds.join(", ")}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="intel-section">
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
          {evidence.map((item) => (
            <article key={item.id}>
              <span>{item.kind}</span>
              <strong>{item.title}</strong>
              <p>{item.summary}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="intel-section split">
        <div>
          <div className="panel-heading">
            <FileText aria-hidden="true" size={17} />
            <h2>Findings</h2>
            <span>{findings.length}</span>
          </div>
          <div className="finding-list">
            {findings.map((finding) => (
              <article key={finding.id}>
                <span>{finding.severity}</span>
                <strong>{finding.title}</strong>
                <small>{finding.status}</small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <div className="panel-heading">
            <Flag aria-hidden="true" size={17} />
            <h2>Flags</h2>
            <span>{flags.length}</span>
          </div>
          <div className="flag-list">
            {flags.map((flag) => (
              <article key={flag.id}>
                <span>{flag.type}</span>
                <strong>{flag.value}</strong>
                <small>{flag.evidenceId}</small>
              </article>
            ))}
          </div>
        </div>
      </section>
    </aside>
  );
}

function TerminalPanel({
  tabs,
  activeTerminalId,
  error,
  disabled,
  onOpenTerminal,
  onSelectTerminal,
  onCloseTerminal,
  onDraftChange,
  onSelectionChange,
  onSubmit,
  onSaveSelection,
}: {
  tabs: TerminalTab[];
  activeTerminalId: string | null;
  error: string | null;
  disabled: boolean;
  onOpenTerminal: () => void;
  onSelectTerminal: (terminalId: string) => void;
  onCloseTerminal: () => void;
  onDraftChange: (terminalId: string, draft: string) => void;
  onSelectionChange: (terminalId: string, selection: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSaveSelection: () => void;
}) {
  const activeTab = tabs.find((tab) => tab.terminalId === activeTerminalId) ?? null;
  return (
    <aside className="terminal-panel" aria-label="Embedded terminal">
      <div className="panel-heading">
        <TerminalIcon aria-hidden="true" size={17} />
        <h2>Terminal</h2>
        <button type="button" className="mini-icon-button" onClick={onOpenTerminal} disabled={disabled} aria-label="Open terminal" title="Open terminal">
          <Plus aria-hidden="true" size={16} />
        </button>
      </div>

      <div className="terminal-tabs" aria-label="Terminal tabs">
        {tabs.map((tab) => (
          <button
            type="button"
            className={tab.terminalId === activeTerminalId ? "active" : ""}
            key={tab.terminalId}
            onClick={() => onSelectTerminal(tab.terminalId)}
          >
            {tab.terminalId.slice(0, 13)}
          </button>
        ))}
      </div>

      {error ? <p className="workspace-error">{error}</p> : null}

      {activeTab ? (
        <>
          <div className="terminal-meta">
            <span>{activeTab.status}</span>
            <small>{activeTab.workingDirectory}</small>
          </div>
          <textarea
            className="terminal-output"
            value={activeTab.output}
            readOnly
            spellCheck={false}
            onSelect={(event) => {
              const target = event.currentTarget;
              onSelectionChange(activeTab.terminalId, target.value.slice(target.selectionStart, target.selectionEnd));
            }}
          />
          <form className="terminal-input-row" onSubmit={onSubmit}>
            <label htmlFor="terminal-input">Terminal input</label>
            <input
              id="terminal-input"
              value={activeTab.draft}
              disabled={activeTab.status === "exited"}
              placeholder="Type a command..."
              onChange={(event) => onDraftChange(activeTab.terminalId, event.target.value)}
            />
            <button type="submit" aria-label="Send terminal input" title="Send terminal input" disabled={activeTab.status === "exited"}>
              <SendHorizontal aria-hidden="true" size={16} />
            </button>
          </form>
          <div className="terminal-actions">
            <button type="button" onClick={onSaveSelection} disabled={!activeTab.selection.trim() || activeTab.commands.length === 0}>
              <Save aria-hidden="true" size={15} />
              <span>Save Evidence</span>
            </button>
            <button type="button" onClick={onCloseTerminal} disabled={activeTab.status === "exited"}>
              <X aria-hidden="true" size={15} />
              <span>Close</span>
            </button>
          </div>
          <div className="command-history">
            {activeTab.commands.map((command) => (
              <article key={command.id}>
                <strong>{command.command}</strong>
                <small>{command.output_summary ?? command.output_ref ?? "running"}</small>
              </article>
            ))}
          </div>
        </>
      ) : (
        <div className="terminal-empty">
          <TerminalIcon aria-hidden="true" size={20} />
          <span>No terminal open</span>
        </div>
      )}
    </aside>
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
