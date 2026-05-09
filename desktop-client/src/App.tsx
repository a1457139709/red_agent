import { useMemo, useState } from "react";
import {
  Bot,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Command,
  Compass,
  Menu,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  Search,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";

type Conversation = {
  id: string;
  title: string;
  target: string;
  mode: string;
  updatedAt: string;
  active: boolean;
};

type MessageRole = "agent" | "operator" | "system";

type ChatMessage = {
  id: string;
  role: MessageRole;
  title?: string;
  body: string;
  meta: string;
  steps?: string[];
};

const conversations: Conversation[] = [
  {
    id: "conv-001",
    title: "Linux target immersion",
    target: "10.10.10.5",
    mode: "Enumeration",
    updatedAt: "Now",
    active: true,
  },
  {
    id: "conv-002",
    title: "Web entry triage",
    target: "demo.internal",
    mode: "Recon",
    updatedAt: "12 min",
    active: false,
  },
  {
    id: "conv-003",
    title: "Privilege path notes",
    target: "lab-host-03",
    mode: "Review",
    updatedAt: "1 hr",
    active: false,
  },
];

const promptSuggestions = [
  "枚举这台靶机的初始攻击面",
  "基于当前目标生成下一步侦察计划",
  "整理刚才的发现并给出优先级",
];

const initialMessages: ChatMessage[] = [
  {
    id: "m-001",
    role: "system",
    body: "Session context locked to Linux target immersion. Static prototype mode is active.",
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
    body:
      "我会先建立目标画像，再按端口、Web 指纹、目录候选和弱配置线索推进。当前原型只展示沉浸式对话主体，真实扫描、Finding、Evidence 和 Task 图后续再接入。",
    meta: "red-code Agent · static",
    steps: ["目标确认", "扫描策略草案", "等待真实后端接入"],
  },
];

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.active) ?? conversations[0],
    [],
  );
  const hasConversation = messages.length > 1;

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
        body:
          "收到。静态原型会保留这条输入，并用本地回复模拟 Agent 对话节奏。真实任务编排、证据沉淀和图谱面板会在下一阶段接入。",
        meta: "red-code Agent · static",
        steps: ["解析意图", "规划动作", "等待后端通道"],
      },
    ]);
    setDraft("");
  };

  return (
    <main className={`immersion-shell ${sidebarOpen ? "sidebar-expanded" : "sidebar-collapsed"}`}>
      <aside className="conversation-rail" aria-label="Conversation management">
        <ConversationPanel
          activeConversationId={activeConversation.id}
          collapsed={!sidebarOpen}
          onCloseMobile={() => setMobileDrawerOpen(false)}
        />
      </aside>

      <div className={`mobile-drawer ${mobileDrawerOpen ? "open" : ""}`} aria-hidden={!mobileDrawerOpen}>
        <div className="mobile-drawer-surface">
          <ConversationPanel
            activeConversationId={activeConversation.id}
            collapsed={false}
            onCloseMobile={() => setMobileDrawerOpen(false)}
          />
        </div>
      </div>

      <section className="agent-workspace" aria-label="Agent conversation">
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
                Static Agent Session
              </span>
              <h1>{activeConversation.title}</h1>
            </div>
          </div>
          <div className="header-status" aria-label="Session status">
            <span>
              <Target aria-hidden="true" size={15} />
              {activeConversation.target}
            </span>
            <span>
              <ShieldCheck aria-hidden="true" size={15} />
              Prototype
            </span>
          </div>
        </header>

        <section className="conversation-stage">
          <div className="stage-scroll">
            <div className="conversation-body">
              {!hasConversation ? <WelcomePanel onPickPrompt={sendMessage} /> : null}
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
          <p>Static immersion prototype. Backend tasks, evidence, findings, and graph views are intentionally deferred.</p>
        </footer>
      </section>
    </main>
  );
}

function ConversationPanel({
  activeConversationId,
  collapsed,
  onCloseMobile,
}: {
  activeConversationId: string;
  collapsed: boolean;
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
              <span>Immersive Agent</span>
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

      {!collapsed ? <p className="rail-section-label">Conversations</p> : null}
      <nav className="conversation-list" aria-label="Conversation list">
        {conversations.map((conversation) => (
          <button
            type="button"
            className={`conversation-item ${conversation.id === activeConversationId ? "active" : ""}`}
            key={conversation.id}
            title={collapsed ? conversation.title : undefined}
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
      </nav>

      {!collapsed ? (
        <div className="rail-footer">
          <Clock3 aria-hidden="true" size={16} />
          <span>Static data · no backend session bound</span>
        </div>
      ) : null}
    </div>
  );
}

function WelcomePanel({onPickPrompt}: { onPickPrompt: (prompt: string) => void }) {
  return (
    <section className="welcome-panel" aria-label="Welcome">
      <div className="welcome-icon" aria-hidden="true">
        <Sparkles size={28} />
      </div>
      <h2>Start with the Agent, not a dashboard.</h2>
      <p>Use the conversation as the main surface. Graphs, evidence, tasks, and findings stay out of this first pass.</p>
      <div className="welcome-prompts">
        {promptSuggestions.map((prompt) => (
          <button type="button" key={prompt} onClick={() => onPickPrompt(prompt)}>
            <Compass aria-hidden="true" size={16} />
            <span>{prompt}</span>
            <ChevronRight aria-hidden="true" size={16} />
          </button>
        ))}
      </div>
    </section>
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
        {message.role === "agent" ? <Bot size={18} /> : <ChevronLeft size={18} />}
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
