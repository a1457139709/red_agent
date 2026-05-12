import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
  Radio,
  Search,
  SendHorizontal,
  ShieldCheck,
  Target,
  X,
} from "lucide-react";
import {
  type AttackPathNodeDto,
  type EvidenceDto,
  type FindingDto,
  type FlagDto,
  type ProjectDto,
  type TargetSessionDto,
  createEvidence,
  getBackendUrl,
  listAttackPath,
  listEvidence,
  listFindings,
  listFlags,
  listProjectSessions,
  listProjects,
} from "./lib/api";

type WorkspaceMode = "Recon" | "Exploit" | "Report";
type MessageRole = "agent" | "operator" | "system";

type Conversation = {
  id: string;
  projectId: string;
  title: string;
  target: string;
  mode: string;
  updatedAt: string;
};

type ChatMessage = {
  id: string;
  role: MessageRole;
  title?: string;
  body: string;
  meta: string;
  steps?: string[];
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

const promptSuggestions = [
  "枚举这台靶机的初始攻击面",
  "基于当前证据生成下一步侦察计划",
  "整理 findings 并给出优先级",
];

const initialMessages: ChatMessage[] = [
  {
    id: "m-001",
    role: "system",
    body: "Session context locked to Linux target immersion.",
    meta: "workspace",
  },
  {
    id: "m-002",
    role: "operator",
    body: "枚举这台靶机的初始攻击面，先给我可执行的步骤。",
    meta: "Operator · just now",
  },
  {
    id: "m-003",
    role: "agent",
    title: "Agent response",
    body: "端口枚举优先，HTTP 服务进入目录发现，POC 命中后沉淀为 finding、evidence 和攻击路径节点。",
    meta: "red-code Agent · local",
    steps: ["Nmap service node", "ffuf web-enum node", "nuclei verified finding"],
  },
];

export function App() {
  const backendUrl = useMemo(() => getBackendUrl(), []);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [mode, setMode] = useState<WorkspaceMode>("Recon");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [nodes, setNodes] = useState<AttackNode[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [flags, setFlags] = useState<FlagItem[]>([]);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [noteSubmitting, setNoteSubmitting] = useState(false);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) ?? null,
    [activeConversationId, conversations],
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
        const sessionGroups = await Promise.all(
          projects.map(async (project) => ({
            project,
            sessions: await listProjectSessions(backendUrl, project.id),
          })),
        );
        if (cancelled) {
          return;
        }
        const nextConversations = sessionGroups.flatMap(({project, sessions}) =>
          sessions.map((session) => mapConversation(project, session)),
        );
        setConversations(nextConversations);
        setActiveConversationId((current) =>
          current && nextConversations.some((conversation) => conversation.id === current)
            ? current
            : nextConversations[0]?.id ?? null,
        );
        if (!nextConversations.length) {
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
    if (!activeConversation) {
      return;
    }
    const sessionId = activeConversation.id;
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
  }, [activeConversation, refreshWorkspace]);

  const sendMessage = (body: string) => {
    const normalized = body.trim();
    if (!normalized) {
      return;
    }
    const createdAt = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    setMessages((current) => [
      ...current,
      {
        id: `operator-${Date.now()}`,
        role: "operator",
        body: normalized,
        meta: `Operator · ${createdAt}`,
      },
      {
        id: `agent-${Date.now()}`,
        role: "agent",
        title: "Agent response",
        body: "我会把新输入作为当前 Session 的分析上下文，并保持 task、evidence、finding 和 attack path 的引用关系。",
        meta: "red-code Agent · local",
        steps: ["更新上下文", "关联证据", "生成下一步"],
      },
    ]);
    setDraft("");
  };

  const createManualNote = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = noteDraft.trim();
    if (!normalized || !activeConversation || noteSubmitting) {
      return;
    }
    setNoteSubmitting(true);
    try {
      await createEvidence(backendUrl, activeConversation.id, {
        evidence_type: "note",
        title: normalized,
        summary: "Manual operator note.",
      });
      setNoteDraft("");
      await refreshWorkspace(activeConversation.id);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to create evidence.");
    } finally {
      setNoteSubmitting(false);
    }
  };

  return (
    <main className={`immersion-shell ${sidebarOpen ? "sidebar-expanded" : "sidebar-collapsed"}`}>
      <aside className="conversation-rail" aria-label="Conversation management">
        <ConversationPanel
          activeConversationId={activeConversationId}
          conversations={conversations}
          collapsed={!sidebarOpen}
          onSelectConversation={setActiveConversationId}
          onCloseMobile={() => setMobileDrawerOpen(false)}
        />
      </aside>

      <div className={`mobile-drawer ${mobileDrawerOpen ? "open" : ""}`} aria-hidden={!mobileDrawerOpen}>
        <div className="mobile-drawer-surface">
          <ConversationPanel
            activeConversationId={activeConversationId}
            conversations={conversations}
            collapsed={false}
            onSelectConversation={setActiveConversationId}
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
                Control Center
              </span>
              <h1>{activeConversation?.title ?? "No session selected"}</h1>
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
              {activeConversation?.target ?? "No target"}
            </span>
            <span>
              <ShieldCheck aria-hidden="true" size={15} />
              Phase 5
            </span>
          </div>
        </header>

        <div className="workspace-grid">
          <section className="conversation-column" aria-label="Agent conversation">
            <section className="conversation-stage">
              <div className="stage-scroll">
                <div className="conversation-body">
                  {messages.map((message) => (
                    <MessageBubble message={message} key={message.id} />
                  ))}
                </div>
              </div>
              <div className="body-fade" aria-hidden="true" />
            </section>

            <footer className="sender-dock">
              <div className="quick-prompts" aria-label="Prompt suggestions">
                {promptSuggestions.map((prompt) => (
                  <button type="button" key={prompt} onClick={() => sendMessage(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  sendMessage(draft);
                }}
              >
                <label htmlFor="agent-draft">Agent prompt</label>
                <textarea
                  id="agent-draft"
                  rows={1}
                  value={draft}
                  placeholder="Ask the Agent to reason about the target..."
                  onChange={(event) => setDraft(event.target.value)}
                />
                <button type="submit" className="send-button" aria-label="Send message" title="Send message">
                  <SendHorizontal aria-hidden="true" size={19} />
                </button>
              </form>
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
            noteDisabled={!activeConversation || noteSubmitting}
            onNoteChange={setNoteDraft}
            onCreateNote={createManualNote}
          />
        </div>
      </section>
    </main>
  );
}

function mapConversation(project: ProjectDto, session: TargetSessionDto): Conversation {
  return {
    id: session.id,
    projectId: project.id,
    title: session.name,
    target: session.target_value,
    mode: `${project.name} · ${session.target_type}`,
    updatedAt: formatCompactTime(session.updated_at),
  };
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

function ConversationPanel({
  activeConversationId,
  conversations,
  collapsed,
  onSelectConversation,
  onCloseMobile,
}: {
  activeConversationId: string | null;
  conversations: Conversation[];
  collapsed: boolean;
  onSelectConversation: (conversationId: string) => void;
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
        <button type="button" className="icon-text-action" aria-label="New conversation" title="New conversation">
          <MessageSquarePlus aria-hidden="true" size={18} />
          {!collapsed ? <span>New Conversation</span> : null}
        </button>
        <button type="button" className="icon-text-action" aria-label="Search conversations" title="Search conversations">
          <Search aria-hidden="true" size={18} />
          {!collapsed ? <span>Search</span> : null}
        </button>
      </div>

      {!collapsed ? <p className="rail-section-label">Sessions</p> : null}
      <nav className="conversation-list" aria-label="Session list">
        {conversations.map((conversation) => (
          <button
            type="button"
            className={`conversation-item ${conversation.id === activeConversationId ? "active" : ""}`}
            key={conversation.id}
            title={collapsed ? conversation.title : undefined}
            onClick={() => {
              onSelectConversation(conversation.id);
              onCloseMobile();
            }}
          >
            <span className="conversation-icon" aria-hidden="true">
              <Command size={16} />
            </span>
            {!collapsed ? (
              <span className="conversation-copy">
                <strong>{conversation.title}</strong>
                <small>{conversation.mode} · {conversation.target}</small>
              </span>
            ) : null}
            {!collapsed ? <span className="conversation-time">{conversation.updatedAt}</span> : null}
          </button>
        ))}
        {!conversations.length ? (
          <div className="conversation-empty">
            {!collapsed ? <span>No persisted sessions</span> : null}
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
