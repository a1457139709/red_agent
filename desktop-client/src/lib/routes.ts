export type WorkspaceRoute = {
  projectId: string | null;
  sessionId: string | null;
};

export function parseWorkspaceHash(hash: string): WorkspaceRoute {
  const normalized = hash.replace(/^#\/?/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts[0] !== "projects" || !parts[1]) {
    return {projectId: null, sessionId: null};
  }
  if (parts[2] === "sessions" && parts[3]) {
    return {projectId: parts[1], sessionId: parts[3]};
  }
  return {projectId: parts[1], sessionId: null};
}

export function projectHash(projectId: string): string {
  return `#/projects/${projectId}`;
}

export function sessionHash(projectId: string, sessionId: string): string {
  return `#/projects/${projectId}/sessions/${sessionId}`;
}
