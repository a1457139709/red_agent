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

export function getBackendUrl(): string {
  return import.meta.env.VITE_BACKEND_URL ?? DEFAULT_BACKEND_URL;
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
  target_value: string;
  target_type: TargetType;
  status: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type SessionDashboardDto = {
  project: ProjectDto;
  session: TargetSessionDto;
  target: {
    value: string;
    type: TargetType;
    summary: string | null;
  };
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

export type CreateProjectInput = {
  name: string;
  description?: string | null;
};

export type CreateTargetSessionInput = {
  name: string;
  target_value: string;
  target_type: TargetType;
  summary?: string | null;
};

export type CreateScanTaskInput = {
  task_type: "port_scan" | "dir_scan" | "poc_scan";
  input: Record<string, unknown>;
};

export type AgentMessageInput = {
  message: string;
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
  const record = requireRecord(payload, "Invalid target session.");
  const targetType = requireString(record.target_type, "Invalid target type.");
  if (!TARGET_TYPES.has(targetType as TargetType)) {
    throw new Error("Invalid target type.");
  }
  return {
    id: requireString(record.id, "Invalid session id."),
    public_id: requireString(record.public_id, "Invalid session public id."),
    project_id: requireString(record.project_id, "Invalid session project id."),
    name: requireString(record.name, "Invalid session name."),
    target_value: requireString(record.target_value, "Invalid target value."),
    target_type: targetType as TargetType,
    status: requireString(record.status, "Invalid session status."),
    summary: requireNullableString(record.summary, "Invalid session summary."),
    created_at: requireString(record.created_at, "Invalid session created_at."),
    updated_at: requireString(record.updated_at, "Invalid session updated_at."),
    metadata: requireRecord(record.metadata, "Invalid session metadata."),
  };
}

export function parseSessionDashboard(payload: unknown): SessionDashboardDto {
  const record = requireRecord(payload, "Invalid session dashboard.");
  const target = requireRecord(record.target, "Invalid dashboard target.");
  const targetType = requireString(target.type, "Invalid dashboard target type.");
  if (!TARGET_TYPES.has(targetType as TargetType)) {
    throw new Error("Invalid dashboard target type.");
  }
  return {
    project: parseProject(record.project),
    session: parseTargetSession(record.session),
    target: {
      value: requireString(target.value, "Invalid dashboard target value."),
      type: targetType as TargetType,
      summary: requireNullableString(target.summary, "Invalid dashboard target summary."),
    },
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

export async function listProjects(baseUrl: string): Promise<ProjectDto[]> {
  const payload = requireRecord(await requestJson(`${baseUrl}/api/projects`), "Invalid projects response.");
  const projects = payload.projects;
  if (!Array.isArray(projects)) {
    throw new Error("Invalid projects response.");
  }
  return projects.map(parseProject);
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

export async function createTargetSession(
  baseUrl: string,
  projectId: string,
  input: CreateTargetSessionInput,
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

async function requestJson(url: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function requireRecord(payload: unknown, message: string): Record<string, unknown> {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload as Record<string, unknown>;
}

function requireRecordArray(payload: unknown, message: string): Record<string, unknown>[] {
  if (!Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload.map((item) => requireRecord(item, message));
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

function requireBoolean(payload: unknown, message: string): boolean {
  if (typeof payload !== "boolean") {
    throw new Error(message);
  }
  return payload;
}
