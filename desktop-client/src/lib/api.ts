export type HealthResponse = {
  status: string;
  service: string;
  started_at: string;
};

export type HealthStatus =
  | { state: "checking" }
  | { state: "online"; payload: HealthResponse }
  | { state: "offline"; error: string };

export const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
export const BACKEND_URL_STORAGE_KEY = "red-code.backend-url";
export const AUTH_TOKEN_STORAGE_KEY = "red-code.auth-token";

let apiAuthToken: string | null = readLocalStorage(AUTH_TOKEN_STORAGE_KEY);

export function getBackendUrl(): string {
  return readLocalStorage(BACKEND_URL_STORAGE_KEY) ?? import.meta.env.VITE_BACKEND_URL ?? DEFAULT_BACKEND_URL;
}

export function setBackendUrl(value: string): string {
  const normalized = normalizeBackendUrl(value);
  writeLocalStorage(BACKEND_URL_STORAGE_KEY, normalized);
  return normalized;
}

export function setApiAuthToken(token: string | null): void {
  apiAuthToken = token;
  if (token) {
    writeLocalStorage(AUTH_TOKEN_STORAGE_KEY, token);
  } else {
    removeLocalStorage(AUTH_TOKEN_STORAGE_KEY);
  }
}

export function getApiAuthToken(): string | null {
  return apiAuthToken;
}

export function normalizeBackendUrl(value: string): string {
  const normalized = value.trim().replace(/\/+$/, "");
  if (!normalized) {
    return DEFAULT_BACKEND_URL;
  }
  const url = new URL(normalized);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Backend URL must use http or https.");
  }
  return url.toString().replace(/\/+$/, "");
}

export function isLocalBackendUrl(value: string): boolean {
  try {
    const hostname = new URL(value).hostname.toLowerCase();
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
  } catch {
    return false;
  }
}

export function parseHealthResponse(payload: unknown): HealthResponse {
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("status" in payload) ||
    !("service" in payload) ||
    !("started_at" in payload)
  ) {
    throw new Error("Invalid health response.");
  }
  const response = payload as Record<string, unknown>;
  if (
    typeof response.status !== "string" ||
    typeof response.service !== "string" ||
    typeof response.started_at !== "string"
  ) {
    throw new Error("Invalid health response fields.");
  }
  return {
    status: response.status,
    service: response.service,
    started_at: response.started_at,
  };
}

export async function fetchHealth(baseUrl: string): Promise<HealthResponse> {
  return parseHealthResponse(await requestJson(`${baseUrl}/api/health`));
}

export type ProjectDto = {
  id: string;
  public_id: string;
  name: string;
  description: string | null;
  root_path: string;
  status: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type TargetType = "ip" | "domain" | "url" | "host" | "note";

export type TargetSessionDto = {
  id: string;
  public_id: string;
  project_id: string;
  name: string;
  status: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type TargetDto = {
  id: string;
  public_id: string;
  project_id: string;
  value: string;
  target_type: TargetType;
  normalized_host: string | null;
  source: string;
  status: "active" | "pending" | "rejected" | "archived";
  confidence: number | null;
  discovered_by: string | null;
  discovered_from: string | null;
  scope_reason: string | null;
  rejection_key: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type SessionDashboardDto = {
  project: ProjectDto;
  session: TargetSessionDto;
  active_targets: Record<string, unknown>[];
  pending_targets: Record<string, unknown>[];
  task_counts: Record<string, number>;
  finding_counts: Record<string, number>;
  evidence_count: number;
  flag_count: number;
  open_ports: Record<string, unknown>[];
  web_entries: Record<string, unknown>[];
  directory_findings: Record<string, unknown>[];
  poc_hits: Record<string, unknown>[];
  attack_path: Record<string, unknown>[];
  recent_commands: Record<string, unknown>[];
  evidence: Record<string, unknown>[];
  flags: Record<string, unknown>[];
  next_actions: Record<string, unknown>[];
};

export type ToolStatusDto = {
  name: "nmap" | "ffuf" | "nuclei";
  available: boolean;
  path: string | null;
  version: string | null;
  error: string | null;
};

export type AuthSessionDto = {
  enabled: boolean;
  authenticated: boolean;
  username: string | null;
};

export type LoginResponseDto = {
  token: string | null;
  auth: AuthSessionDto;
};

export type ToolName = "nmap" | "ffuf" | "nuclei";

export type ScannerToolConfigDto = {
  binary_path: string | null;
  timeout_seconds: number;
  templates_path: string | null;
  default_wordlist: string | null;
  extra_args: string[];
};

export type ToolConfigDto = {
  tools: Record<ToolName, ScannerToolConfigDto>;
};

export type ScanTaskDto = {
  id: string;
  public_id: string;
  project_id: string;
  session_id: string;
  task_type: string;
  executor: string;
  status: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
  started_at: string | null;
  ended_at: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type EvidenceDto = {
  id: string;
  public_id: string;
  project_id: string;
  session_id: string;
  source_task_id: string | null;
  evidence_type: string;
  title: string;
  summary: string | null;
  content_ref: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AttackPathNodeDto = {
  id: string;
  public_id: string;
  project_id: string;
  session_id: string;
  stage: string;
  title: string;
  status: string;
  source_ref: string | null;
  next_action: string | null;
  created_at: string;
  evidence: EvidenceDto[];
};

export type FindingDto = {
  id: string;
  public_id: string;
  project_id: string;
  session_id: string;
  severity: string;
  status: string;
  title: string;
  description: string | null;
  evidence_refs: string[];
  created_at: string;
  updated_at: string;
};

export type FlagDto = {
  id: string;
  public_id: string;
  project_id: string;
  session_id: string;
  flag_type: string;
  value: string;
  source_evidence_id: string | null;
  created_at: string;
};

export type ReportDto = {
  id: string;
  public_id: string;
  project_id: string;
  session_id: string | null;
  report_type: string;
  title: string;
  summary: string;
  material_path: string;
  artifact_path: string;
  created_at: string;
  metadata: Record<string, unknown>;
  content: string | null;
};

export type TerminalDto = {
  terminal_id: string;
  project_id: string;
  session_id: string;
  working_directory: string;
  status: string;
  created_at: string;
};

export type CommandRunDto = {
  id: string;
  public_id: string;
  project_id: string;
  session_id: string;
  terminal_id: string;
  command: string;
  exit_code: number | null;
  output_ref: string | null;
  output_summary: string | null;
  working_directory: string | null;
  tags: string[];
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
};

export type CreateProjectInput = {
  name: string;
  description?: string | null;
};

export type CreateTargetSessionInput = Record<string, never>;

export type CreateScanTaskInput = {
  task_type: "port_scan" | "dir_scan" | "poc_scan";
  input: Record<string, unknown>;
};

export type AgentMessageInput = {
  message: string;
};

export type CreateEvidenceInput = {
  evidence_type: string;
  title: string;
  summary?: string | null;
  content_ref?: string | null;
  payload?: Record<string, unknown>;
  source_task_id?: string | null;
  attack_path_node_id?: string | null;
};

export type CreateAttackPathNodeInput = {
  stage: string;
  title: string;
  status?: string;
  source_ref?: string | null;
  next_action?: string | null;
  evidence_ids?: string[];
};

export type CreateFlagInput = {
  flag_type: string;
  value: string;
  source_evidence_id?: string | null;
};

export type OpenTerminalInput = {
  rows?: number;
  cols?: number;
};

export type CreateCommandEvidenceInput = {
  title: string;
  selected_text: string;
  summary?: string | null;
  attack_path_node_id?: string | null;
  tags?: string[];
};

const TARGET_TYPES = new Set<TargetType>(["ip", "domain", "url", "host", "note"]);
const TOOL_NAMES = new Set(["nmap", "ffuf", "nuclei"]);

export function parseProject(payload: unknown): ProjectDto {
  const record = requireRecord(payload, "Invalid project.");
  return {
    id: requireString(record.id, "Invalid project id."),
    public_id: requireString(record.public_id, "Invalid project public id."),
    name: requireString(record.name, "Invalid project name."),
    description: requireNullableString(record.description, "Invalid project description."),
    root_path: requireString(record.root_path, "Invalid project root path."),
    status: requireString(record.status, "Invalid project status."),
    created_at: requireString(record.created_at, "Invalid project created_at."),
    updated_at: requireString(record.updated_at, "Invalid project updated_at."),
    metadata: requireRecord(record.metadata, "Invalid project metadata."),
  };
}

export function parseTargetSession(payload: unknown): TargetSessionDto {
  const record = requireRecord(payload, "Invalid session.");
  return {
    id: requireString(record.id, "Invalid session id."),
    public_id: requireString(record.public_id, "Invalid session public id."),
    project_id: requireString(record.project_id, "Invalid session project id."),
    name: requireString(record.name, "Invalid session name."),
    status: requireString(record.status, "Invalid session status."),
    summary: requireNullableString(record.summary, "Invalid session summary."),
    created_at: requireString(record.created_at, "Invalid session created_at."),
    updated_at: requireString(record.updated_at, "Invalid session updated_at."),
    metadata: requireRecord(record.metadata, "Invalid session metadata."),
  };
}

export function parseTarget(payload: unknown): TargetDto {
  const record = requireRecord(payload, "Invalid target.");
  const targetType = requireString(record.target_type, "Invalid target type.");
  if (!TARGET_TYPES.has(targetType as TargetType)) {
    throw new Error("Invalid target type.");
  }
  const status = requireString(record.status, "Invalid target status.");
  if (!["active", "pending", "rejected", "archived"].includes(status)) {
    throw new Error("Invalid target status.");
  }
  return {
    id: requireString(record.id, "Invalid target id."),
    public_id: requireString(record.public_id, "Invalid target public id."),
    project_id: requireString(record.project_id, "Invalid target project id."),
    value: requireString(record.value, "Invalid target value."),
    target_type: targetType as TargetType,
    normalized_host: requireNullableString(record.normalized_host, "Invalid target host."),
    source: requireString(record.source, "Invalid target source."),
    status: status as TargetDto["status"],
    confidence: typeof record.confidence === "number" ? record.confidence : null,
    discovered_by: requireNullableString(record.discovered_by, "Invalid target discovered_by."),
    discovered_from: requireNullableString(record.discovered_from, "Invalid target discovered_from."),
    scope_reason: requireNullableString(record.scope_reason, "Invalid target scope reason."),
    rejection_key: requireNullableString(record.rejection_key, "Invalid target rejection key."),
    created_at: requireString(record.created_at, "Invalid target created_at."),
    updated_at: requireString(record.updated_at, "Invalid target updated_at."),
    metadata: requireRecord(record.metadata, "Invalid target metadata."),
  };
}

export function parseSessionDashboard(payload: unknown): SessionDashboardDto {
  const record = requireRecord(payload, "Invalid session dashboard.");
  return {
    project: parseProject(record.project),
    session: parseTargetSession(record.session),
    active_targets: requireRecordArray(record.active_targets ?? [], "Invalid dashboard active targets."),
    pending_targets: requireRecordArray(record.pending_targets ?? [], "Invalid dashboard pending targets."),
    task_counts: requireNumberRecord(record.task_counts, "Invalid task counts."),
    finding_counts: requireNumberRecord(record.finding_counts, "Invalid finding counts."),
    evidence_count: requireNumber(record.evidence_count, "Invalid evidence count."),
    flag_count: requireNumber(record.flag_count, "Invalid flag count."),
    open_ports: requireRecordArray(record.open_ports, "Invalid open ports."),
    web_entries: requireRecordArray(record.web_entries, "Invalid web entries."),
    directory_findings: requireRecordArray(record.directory_findings, "Invalid directory findings."),
    poc_hits: requireRecordArray(record.poc_hits, "Invalid POC hits."),
    attack_path: requireRecordArray(record.attack_path, "Invalid attack path."),
    recent_commands: requireRecordArray(record.recent_commands, "Invalid recent commands."),
    evidence: requireRecordArray(record.evidence, "Invalid evidence."),
    flags: requireRecordArray(record.flags, "Invalid flags."),
    next_actions: requireRecordArray(record.next_actions, "Invalid next actions."),
  };
}

export function parseToolStatus(payload: unknown): ToolStatusDto {
  const record = requireRecord(payload, "Invalid tool status.");
  const name = requireString(record.name, "Invalid tool name.");
  if (!TOOL_NAMES.has(name)) {
    throw new Error("Invalid tool name.");
  }
  return {
    name: name as ToolStatusDto["name"],
    available: requireBoolean(record.available, "Invalid tool availability."),
    path: requireNullableString(record.path, "Invalid tool path."),
    version: requireNullableString(record.version, "Invalid tool version."),
    error: requireNullableString(record.error, "Invalid tool error."),
  };
}

export function parseAuthSession(payload: unknown): AuthSessionDto {
  const record = requireRecord(payload, "Invalid auth session.");
  return {
    enabled: requireBoolean(record.enabled, "Invalid auth enabled flag."),
    authenticated: requireBoolean(record.authenticated, "Invalid auth authenticated flag."),
    username: requireNullableString(record.username, "Invalid auth username."),
  };
}

export function parseLoginResponse(payload: unknown): LoginResponseDto {
  const record = requireRecord(payload, "Invalid login response.");
  return {
    token: requireNullableString(record.token, "Invalid auth token."),
    auth: parseAuthSession(record.auth),
  };
}

export function parseToolConfig(payload: unknown): ToolConfigDto {
  const record = requireRecord(payload, "Invalid tool config.");
  const tools = requireRecord(record.tools, "Invalid tool config tools.");
  return {
    tools: {
      nmap: parseScannerToolConfig(tools.nmap),
      ffuf: parseScannerToolConfig(tools.ffuf),
      nuclei: parseScannerToolConfig(tools.nuclei),
    },
  };
}

export function parseScanTask(payload: unknown): ScanTaskDto {
  const record = requireRecord(payload, "Invalid scan task.");
  return {
    id: requireString(record.id, "Invalid task id."),
    public_id: requireString(record.public_id, "Invalid task public id."),
    project_id: requireString(record.project_id, "Invalid task project id."),
    session_id: requireString(record.session_id, "Invalid task session id."),
    task_type: requireString(record.task_type, "Invalid task type."),
    executor: requireString(record.executor, "Invalid task executor."),
    status: requireString(record.status, "Invalid task status."),
    input: requireRecord(record.input, "Invalid task input."),
    result: requireRecord(record.result, "Invalid task result."),
    started_at: requireNullableString(record.started_at, "Invalid task started_at."),
    ended_at: requireNullableString(record.ended_at, "Invalid task ended_at."),
    error: requireNullableString(record.error, "Invalid task error."),
    created_at: requireString(record.created_at, "Invalid task created_at."),
    updated_at: requireString(record.updated_at, "Invalid task updated_at."),
  };
}

export function parseEvidence(payload: unknown): EvidenceDto {
  const record = requireRecord(payload, "Invalid evidence.");
  return {
    id: requireString(record.id, "Invalid evidence id."),
    public_id: requireString(record.public_id, "Invalid evidence public id."),
    project_id: requireString(record.project_id, "Invalid evidence project id."),
    session_id: requireString(record.session_id, "Invalid evidence session id."),
    source_task_id: requireNullableString(record.source_task_id, "Invalid evidence source task id."),
    evidence_type: requireString(record.evidence_type, "Invalid evidence type."),
    title: requireString(record.title, "Invalid evidence title."),
    summary: requireNullableString(record.summary, "Invalid evidence summary."),
    content_ref: requireNullableString(record.content_ref, "Invalid evidence content ref."),
    payload: requireRecord(record.payload, "Invalid evidence payload."),
    created_at: requireString(record.created_at, "Invalid evidence created_at."),
  };
}

export function parseAttackPathNode(payload: unknown): AttackPathNodeDto {
  const record = requireRecord(payload, "Invalid attack path node.");
  return {
    id: requireString(record.id, "Invalid attack path node id."),
    public_id: requireString(record.public_id, "Invalid attack path node public id."),
    project_id: requireString(record.project_id, "Invalid attack path node project id."),
    session_id: requireString(record.session_id, "Invalid attack path node session id."),
    stage: requireString(record.stage, "Invalid attack path node stage."),
    title: requireString(record.title, "Invalid attack path node title."),
    status: requireString(record.status, "Invalid attack path node status."),
    source_ref: requireNullableString(record.source_ref, "Invalid attack path node source ref."),
    next_action: requireNullableString(record.next_action, "Invalid attack path node next action."),
    created_at: requireString(record.created_at, "Invalid attack path node created_at."),
    evidence: requireArray(record.evidence, "Invalid attack path node evidence.").map(parseEvidence),
  };
}

export function parseFinding(payload: unknown): FindingDto {
  const record = requireRecord(payload, "Invalid finding.");
  return {
    id: requireString(record.id, "Invalid finding id."),
    public_id: requireString(record.public_id, "Invalid finding public id."),
    project_id: requireString(record.project_id, "Invalid finding project id."),
    session_id: requireString(record.session_id, "Invalid finding session id."),
    severity: requireString(record.severity, "Invalid finding severity."),
    status: requireString(record.status, "Invalid finding status."),
    title: requireString(record.title, "Invalid finding title."),
    description: requireNullableString(record.description, "Invalid finding description."),
    evidence_refs: requireStringArray(record.evidence_refs, "Invalid finding evidence refs."),
    created_at: requireString(record.created_at, "Invalid finding created_at."),
    updated_at: requireString(record.updated_at, "Invalid finding updated_at."),
  };
}

export function parseFlag(payload: unknown): FlagDto {
  const record = requireRecord(payload, "Invalid flag.");
  return {
    id: requireString(record.id, "Invalid flag id."),
    public_id: requireString(record.public_id, "Invalid flag public id."),
    project_id: requireString(record.project_id, "Invalid flag project id."),
    session_id: requireString(record.session_id, "Invalid flag session id."),
    flag_type: requireString(record.flag_type, "Invalid flag type."),
    value: requireString(record.value, "Invalid flag value."),
    source_evidence_id: requireNullableString(record.source_evidence_id, "Invalid flag source evidence id."),
    created_at: requireString(record.created_at, "Invalid flag created_at."),
  };
}

export function parseReport(payload: unknown): ReportDto {
  const record = requireRecord(payload, "Invalid report.");
  return {
    id: requireString(record.id, "Invalid report id."),
    public_id: requireString(record.public_id, "Invalid report public id."),
    project_id: requireString(record.project_id, "Invalid report project id."),
    session_id: requireNullableString(record.session_id, "Invalid report session id."),
    report_type: requireString(record.report_type, "Invalid report type."),
    title: requireString(record.title, "Invalid report title."),
    summary: requireString(record.summary, "Invalid report summary."),
    material_path: requireString(record.material_path, "Invalid report material path."),
    artifact_path: requireString(record.artifact_path, "Invalid report artifact path."),
    created_at: requireString(record.created_at, "Invalid report created_at."),
    metadata: requireRecord(record.metadata, "Invalid report metadata."),
    content: "content" in record ? requireNullableString(record.content, "Invalid report content.") : null,
  };
}

export function parseTerminal(payload: unknown): TerminalDto {
  const record = requireRecord(payload, "Invalid terminal.");
  return {
    terminal_id: requireString(record.terminal_id, "Invalid terminal id."),
    project_id: requireString(record.project_id, "Invalid terminal project id."),
    session_id: requireString(record.session_id, "Invalid terminal session id."),
    working_directory: requireString(record.working_directory, "Invalid terminal working directory."),
    status: requireString(record.status, "Invalid terminal status."),
    created_at: requireString(record.created_at, "Invalid terminal created_at."),
  };
}

export function parseCommandRun(payload: unknown): CommandRunDto {
  const record = requireRecord(payload, "Invalid command run.");
  return {
    id: requireString(record.id, "Invalid command id."),
    public_id: requireString(record.public_id, "Invalid command public id."),
    project_id: requireString(record.project_id, "Invalid command project id."),
    session_id: requireString(record.session_id, "Invalid command session id."),
    terminal_id: requireString(record.terminal_id, "Invalid command terminal id."),
    command: requireString(record.command, "Invalid command text."),
    exit_code: requireNullableNumber(record.exit_code, "Invalid command exit code."),
    output_ref: requireNullableString(record.output_ref, "Invalid command output ref."),
    output_summary: requireNullableString(record.output_summary, "Invalid command output summary."),
    working_directory: requireNullableString(record.working_directory, "Invalid command working directory."),
    tags: requireStringArray(record.tags, "Invalid command tags."),
    started_at: requireNullableString(record.started_at, "Invalid command started_at."),
    ended_at: requireNullableString(record.ended_at, "Invalid command ended_at."),
    created_at: requireString(record.created_at, "Invalid command created_at."),
  };
}

export async function listProjects(baseUrl: string): Promise<ProjectDto[]> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/projects`), "Invalid projects response.");
  const projects = payload.projects;
  if (!Array.isArray(projects)) {
    throw new Error("Invalid projects response.");
  }
  return projects.map(parseProject);
}

export async function getAuthSession(baseUrl: string): Promise<AuthSessionDto> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/auth/session`), "Invalid auth session response.");
  return parseAuthSession(payload.auth);
}

export async function login(baseUrl: string, input: {username: string; password: string}): Promise<LoginResponseDto> {
  const payload = await requestJson(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(input),
  });
  const response = parseLoginResponse(payload);
  setApiAuthToken(response.token);
  return response;
}

export async function logout(baseUrl: string): Promise<AuthSessionDto> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/auth/logout`, {method: "POST"}), "Invalid logout response.");
  setApiAuthToken(null);
  return parseAuthSession(payload.auth);
}

export async function createProject(baseUrl: string, input: CreateProjectInput): Promise<ProjectDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/projects`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid project response.",
  );
  return parseProject(payload.project);
}

export async function getProject(baseUrl: string, projectId: string): Promise<ProjectDto> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/projects/${projectId}`), "Invalid project response.");
  return parseProject(payload.project);
}

export async function listProjectSessions(baseUrl: string, projectId: string): Promise<TargetSessionDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/projects/${projectId}/sessions`),
    "Invalid sessions response.",
  );
  const sessions = payload.sessions;
  if (!Array.isArray(sessions)) {
    throw new Error("Invalid sessions response.");
  }
  return sessions.map(parseTargetSession);
}

export async function listProjectTargets(baseUrl: string, projectId: string): Promise<TargetDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/projects/${projectId}/targets`),
    "Invalid targets response.",
  );
  if (!Array.isArray(payload.targets)) {
    throw new Error("Invalid targets response.");
  }
  return payload.targets.map(parseTarget);
}

export async function createTargetSession(
  baseUrl: string,
  projectId: string,
  input: CreateTargetSessionInput = {},
): Promise<TargetSessionDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/projects/${projectId}/sessions`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid session response.",
  );
  return parseTargetSession(payload.session);
}

export async function getTargetSession(baseUrl: string, sessionId: string): Promise<TargetSessionDto> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/sessions/${sessionId}`), "Invalid session response.");
  return parseTargetSession(payload.session);
}

export async function getSessionDashboard(baseUrl: string, sessionId: string): Promise<SessionDashboardDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/dashboard`),
    "Invalid dashboard response.",
  );
  return parseSessionDashboard(payload.dashboard);
}

export async function listToolStatus(baseUrl: string): Promise<ToolStatusDto[]> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/tools/status`), "Invalid tool status response.");
  if (!Array.isArray(payload.tools)) {
    throw new Error("Invalid tool status response.");
  }
  return payload.tools.map(parseToolStatus);
}

export async function getToolConfig(baseUrl: string): Promise<ToolConfigDto> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/tools/config`), "Invalid tool config response.");
  return parseToolConfig(payload.config);
}

export async function updateToolConfig(baseUrl: string, input: ToolConfigDto): Promise<ToolConfigDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/tools/config`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid tool config response.",
  );
  return parseToolConfig(payload.config);
}

export async function listSessionTasks(baseUrl: string, sessionId: string): Promise<ScanTaskDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/tasks`),
    "Invalid tasks response.",
  );
  if (!Array.isArray(payload.tasks)) {
    throw new Error("Invalid tasks response.");
  }
  return payload.tasks.map(parseScanTask);
}

export async function createScanTask(
  baseUrl: string,
  sessionId: string,
  input: CreateScanTaskInput,
): Promise<ScanTaskDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/tasks`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid task response.",
  );
  return parseScanTask(payload.task);
}

export async function cancelScanTask(baseUrl: string, taskId: string): Promise<ScanTaskDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/tasks/${taskId}/cancel`, {method: "POST"}),
    "Invalid task response.",
  );
  return parseScanTask(payload.task);
}

export async function rerunScanTask(baseUrl: string, taskId: string): Promise<ScanTaskDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/tasks/${taskId}/rerun`, {method: "POST"}),
    "Invalid task response.",
  );
  return parseScanTask(payload.task);
}

export async function sendAgentMessage(
  baseUrl: string,
  sessionId: string,
  input: AgentMessageInput,
): Promise<ScanTaskDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/agent/messages`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid agent task response.",
  );
  return parseScanTask(payload.task);
}

export async function listAttackPath(baseUrl: string, sessionId: string): Promise<AttackPathNodeDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/attack-path`),
    "Invalid attack path response.",
  );
  return requireArray(payload.nodes, "Invalid attack path response.").map(parseAttackPathNode);
}

export async function createAttackPathNode(
  baseUrl: string,
  sessionId: string,
  input: CreateAttackPathNodeInput,
): Promise<AttackPathNodeDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/attack-path`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid attack path node response.",
  );
  return parseAttackPathNode(payload.node);
}

export async function listEvidence(baseUrl: string, sessionId: string): Promise<EvidenceDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/evidence`),
    "Invalid evidence response.",
  );
  return requireArray(payload.evidence, "Invalid evidence response.").map(parseEvidence);
}

export async function createEvidence(
  baseUrl: string,
  sessionId: string,
  input: CreateEvidenceInput,
): Promise<{evidence: EvidenceDto; node: AttackPathNodeDto}> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/evidence`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid evidence response.",
  );
  return {evidence: parseEvidence(payload.evidence), node: parseAttackPathNode(payload.node)};
}

export async function listFindings(baseUrl: string, sessionId: string): Promise<FindingDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/findings`),
    "Invalid findings response.",
  );
  return requireArray(payload.findings, "Invalid findings response.").map(parseFinding);
}

export async function listFlags(baseUrl: string, sessionId: string): Promise<FlagDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/flags`),
    "Invalid flags response.",
  );
  return requireArray(payload.flags, "Invalid flags response.").map(parseFlag);
}

export async function createFlag(
  baseUrl: string,
  sessionId: string,
  input: CreateFlagInput,
): Promise<{flag: FlagDto; node: AttackPathNodeDto}> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/flags`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid flag response.",
  );
  return {flag: parseFlag(payload.flag), node: parseAttackPathNode(payload.node)};
}

export async function listSessionReports(baseUrl: string, sessionId: string): Promise<ReportDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/reports`),
    "Invalid reports response.",
  );
  return requireArray(payload.reports, "Invalid reports response.").map(parseReport);
}

export async function listProjectReports(baseUrl: string, projectId: string): Promise<ReportDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/projects/${projectId}/reports`),
    "Invalid project reports response.",
  );
  return requireArray(payload.reports, "Invalid project reports response.").map(parseReport);
}

export async function createSessionReport(baseUrl: string, sessionId: string): Promise<ReportDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/reports`, {method: "POST"}),
    "Invalid report response.",
  );
  return parseReport(payload.report);
}

export async function createProjectReport(baseUrl: string, projectId: string): Promise<ReportDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/projects/${projectId}/reports`, {method: "POST"}),
    "Invalid project report response.",
  );
  return parseReport(payload.report);
}

export function reportDownloadUrl(baseUrl: string, reportId: string): string {
  return `${baseUrl}/api/reports/${reportId}/download`;
}

export async function openTerminal(
  baseUrl: string,
  sessionId: string,
  input: OpenTerminalInput = {},
): Promise<TerminalDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/terminals`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid terminal response.",
  );
  return parseTerminal(payload.terminal);
}

export async function listTerminalCommands(baseUrl: string, terminalId: string): Promise<CommandRunDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/terminals/${terminalId}/commands`),
    "Invalid terminal command response.",
  );
  return requireArray(payload.commands, "Invalid terminal command response.").map(parseCommandRun);
}

export async function listSessionCommands(baseUrl: string, sessionId: string): Promise<CommandRunDto[]> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/sessions/${sessionId}/commands`),
    "Invalid session command response.",
  );
  return requireArray(payload.commands, "Invalid session command response.").map(parseCommandRun);
}

export async function createCommandEvidence(
  baseUrl: string,
  commandRunId: string,
  input: CreateCommandEvidenceInput,
): Promise<EvidenceDto> {
  const payload = requireRecord(
    await requestJson(`${baseUrl}/api/commands/${commandRunId}/evidence`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input),
    }),
    "Invalid command evidence response.",
  );
  return parseEvidence(payload.evidence);
}

async function requestJson(url: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(url, withAuthHeader(init));
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json();
}

function withAuthHeader(init?: RequestInit): RequestInit | undefined {
  if (!apiAuthToken) {
    return init;
  }
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${apiAuthToken}`);
  return {...init, headers};
}

async function responseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.clone().json();
    if (typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string") {
      return `Request failed: ${response.status} ${payload.detail}`;
    }
  } catch {
    return `Request failed: ${response.status}`;
  }
  return `Request failed: ${response.status}`;
}

function parseScannerToolConfig(payload: unknown): ScannerToolConfigDto {
  const record = requireRecord(payload, "Invalid scanner tool config.");
  return {
    binary_path: requireNullableString(record.binary_path, "Invalid binary path."),
    timeout_seconds: requireNumber(record.timeout_seconds, "Invalid timeout."),
    templates_path: requireNullableString(record.templates_path, "Invalid templates path."),
    default_wordlist: requireNullableString(record.default_wordlist, "Invalid default wordlist."),
    extra_args: requireStringArray(record.extra_args, "Invalid extra args."),
  };
}

function readLocalStorage(key: string): string | null {
  try {
    return globalThis.localStorage?.getItem(key) || null;
  } catch {
    return null;
  }
}

function writeLocalStorage(key: string, value: string): void {
  try {
    globalThis.localStorage?.setItem(key, value);
  } catch {
    return;
  }
}

function removeLocalStorage(key: string): void {
  try {
    globalThis.localStorage?.removeItem(key);
  } catch {
    return;
  }
}

function requireRecord(payload: unknown, message: string): Record<string, unknown> {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload as Record<string, unknown>;
}

function requireRecordArray(payload: unknown, message: string): Record<string, unknown>[] {
  return requireArray(payload, message).map((item) => requireRecord(item, message));
}

function requireNumberRecord(payload: unknown, message: string): Record<string, number> {
  const record = requireRecord(payload, message);
  for (const value of Object.values(record)) {
    if (typeof value !== "number") {
      throw new Error(message);
    }
  }
  return record as Record<string, number>;
}

function requireString(payload: unknown, message: string): string {
  if (typeof payload !== "string") {
    throw new Error(message);
  }
  return payload;
}

function requireNullableString(payload: unknown, message: string): string | null {
  if (payload === null) {
    return null;
  }
  if (typeof payload !== "string") {
    throw new Error(message);
  }
  return payload;
}

function requireNumber(payload: unknown, message: string): number {
  if (typeof payload !== "number") {
    throw new Error(message);
  }
  return payload;
}

function requireNullableNumber(payload: unknown, message: string): number | null {
  if (payload === null) {
    return null;
  }
  return requireNumber(payload, message);
}

function requireBoolean(payload: unknown, message: string): boolean {
  if (typeof payload !== "boolean") {
    throw new Error(message);
  }
  return payload;
}

function requireArray(payload: unknown, message: string): unknown[] {
  if (!Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload;
}

function requireStringArray(payload: unknown, message: string): string[] {
  return requireArray(payload, message).map((item) => requireString(item, message));
}
