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
  const response = await fetch(`${baseUrl}/api/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return parseHealthResponse(await response.json());
}
