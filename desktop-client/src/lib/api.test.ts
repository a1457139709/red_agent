import { describe, expect, it } from "vitest";
import {
  parseAttackPathNode,
  parseEvidence,
  parseFinding,
  parseFlag,
  parseHealthResponse,
  parseProject,
  parseCommandRun,
  parseScanTask,
  parseSessionDashboard,
  parseTargetSession,
  parseTerminal,
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

describe("phase 5 DTO parsers", () => {
  const evidence = {
    id: "evidence-1",
    public_id: "EVID0001",
    project_id: "project-1",
    session_id: "session-1",
    source_task_id: null,
    evidence_type: "note",
    title: "Manual note",
    summary: "Check login.",
    content_ref: null,
    payload: {},
    created_at: "2026-05-03T00:00:00+00:00",
  };

  it("parses evidence, attack path, finding, and flag DTOs", () => {
    expect(parseEvidence(evidence).public_id).toBe("EVID0001");
    expect(
      parseAttackPathNode({
        id: "node-1",
        public_id: "AP0001",
        project_id: "project-1",
        session_id: "session-1",
        stage: "note",
        title: "Manual note",
        status: "open",
        source_ref: "evidence-1",
        next_action: null,
        created_at: "2026-05-03T00:00:00+00:00",
        evidence: [evidence],
      }).evidence[0].id,
    ).toBe("evidence-1");
    expect(
      parseFinding({
        id: "finding-1",
        public_id: "FIND0001",
        project_id: "project-1",
        session_id: "session-1",
        severity: "medium",
        status: "verified",
        title: "Nuclei match",
        description: null,
        evidence_refs: ["evidence-1"],
        created_at: "2026-05-03T00:00:00+00:00",
        updated_at: "2026-05-03T00:00:00+00:00",
      }).evidence_refs,
    ).toEqual(["evidence-1"]);
    expect(
      parseFlag({
        id: "flag-1",
        public_id: "FLAG0001",
        project_id: "project-1",
        session_id: "session-1",
        flag_type: "loot",
        value: "admin:admin",
        source_evidence_id: "evidence-1",
        created_at: "2026-05-03T00:00:00+00:00",
      }).source_evidence_id,
    ).toBe("evidence-1");
  });
});

describe("phase 6 DTO parsers", () => {
  it("parses terminal and command run DTOs", () => {
    expect(
      parseTerminal({
        terminal_id: "term-1",
        project_id: "project-1",
        session_id: "session-1",
        working_directory: "/tmp/session",
        status: "open",
        created_at: "2026-05-12T00:00:00+00:00",
      }).terminal_id,
    ).toBe("term-1");
    expect(
      parseCommandRun({
        id: "command-1",
        public_id: "CMD0001",
        project_id: "project-1",
        session_id: "session-1",
        terminal_id: "term-1",
        command: "id",
        exit_code: null,
        output_ref: "artifacts/terminal/term-1/id.txt",
        output_summary: "uid=1000",
        working_directory: "/tmp/session",
        tags: ["manual"],
        started_at: "2026-05-12T00:00:00+00:00",
        ended_at: null,
        created_at: "2026-05-12T00:00:00+00:00",
      }).output_summary,
    ).toBe("uid=1000");
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
