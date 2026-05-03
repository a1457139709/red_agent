import { describe, expect, it } from "vitest";
import {
  parseHealthResponse,
  parseProject,
  parseScanTask,
  parseSessionDashboard,
  parseTargetSession,
  parseToolStatus,
} from "./api";

describe("parseHealthResponse", () => {
  it("parses the backend health response", () => {
    expect(
      parseHealthResponse({
        status: "ok",
        service: "control-center",
        started_at: "2026-05-03T00:00:00+00:00",
      }),
    ).toEqual({
      status: "ok",
      service: "control-center",
      started_at: "2026-05-03T00:00:00+00:00",
    });
  });

  it("rejects malformed payloads", () => {
    expect(() => parseHealthResponse({ status: "ok" })).toThrow("Invalid health response");
  });
});

describe("phase 3 DTO parsers", () => {
  it("parses tool status and scan task DTOs", () => {
    expect(parseToolStatus({name: "nmap", available: false, path: null, version: null, error: "missing"})).toEqual({
      name: "nmap",
      available: false,
      path: null,
      version: null,
      error: "missing",
    });
    expect(
      parseScanTask({
        id: "task-1",
        public_id: "TASK0001",
        project_id: "project-1",
        session_id: "session-1",
        task_type: "port_scan",
        executor: "nmap",
        status: "succeeded",
        input: {target_host: "10.10.10.5"},
        result: {structured: {open_ports: []}},
        started_at: null,
        ended_at: null,
        error: null,
        created_at: "2026-05-03T00:00:00+00:00",
        updated_at: "2026-05-03T00:00:00+00:00",
      }).executor,
    ).toBe("nmap");
  });
});

const project = {
  id: "project-1",
  public_id: "P0001",
  name: "HTB Lab",
  description: null,
  root_path: "/tmp/.red-code/projects/project-1",
  status: "active",
  created_at: "2026-05-03T00:00:00+00:00",
  updated_at: "2026-05-03T00:00:00+00:00",
  metadata: {},
};

const session = {
  id: "session-1",
  public_id: "T0001",
  project_id: "project-1",
  name: "Linux target",
  target_value: "10.10.10.5",
  target_type: "ip",
  status: "active",
  summary: null,
  created_at: "2026-05-03T00:00:00+00:00",
  updated_at: "2026-05-03T00:00:00+00:00",
  metadata: {},
};

describe("control center DTO parsers", () => {
  it("parses project and target session DTOs", () => {
    expect(parseProject(project).public_id).toBe("P0001");
    expect(parseTargetSession(session).target_type).toBe("ip");
  });

  it("parses an empty dashboard DTO", () => {
    const dashboard = parseSessionDashboard({
      project,
      session,
      target: {value: "10.10.10.5", type: "ip", summary: null},
      task_counts: {},
      finding_counts: {},
      evidence_count: 0,
      flag_count: 0,
      open_ports: [],
      web_entries: [],
      directory_findings: [],
      poc_hits: [],
      attack_path: [],
      recent_commands: [],
      evidence: [],
      flags: [],
      next_actions: [],
    });

    expect(dashboard.open_ports).toEqual([]);
    expect(dashboard.evidence_count).toBe(0);
  });

  it("rejects invalid target types", () => {
    expect(() => parseTargetSession({...session, target_type: "invalid"})).toThrow("Invalid target type");
  });
});
