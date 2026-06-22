import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_TOKEN_STORAGE_KEY,
  BACKEND_URL_STORAGE_KEY,
  createProject,
  createProjectReport,
  createSessionReport,
  createTargetSession,
  getBackendUrl,
  getToolConfig,
  isLocalBackendUrl,
  login,
  parseAttackPathNode,
  parseAuthSession,
  parseEvidence,
  parseFinding,
  parseFlag,
  parseHealthResponse,
  parseLoginResponse,
  parseProject,
  parseCommandRun,
  parseReport,
  parseScanTask,
  parseSessionDashboard,
  parseTargetSession,
  parseTerminal,
  parseToolConfig,
  parseToolStatus,
  listProjectReports,
  reportDownloadUrl,
  sendAgentMessage,
  setApiAuthToken,
  setBackendUrl,
  updateToolConfig,
} from "./api";

let storage: Map<string, string>;

beforeEach(() => {
  storage = new Map();
  vi.stubGlobal("localStorage", {
    getItem: vi.fn((key: string) => storage.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
    removeItem: vi.fn((key: string) => storage.delete(key)),
  });
});

afterEach(() => {
  setApiAuthToken(null);
  vi.unstubAllGlobals();
});

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

describe("phase 8 auth and tool DTO parsers", () => {
  it("parses auth session and login responses", () => {
    expect(parseAuthSession({enabled: true, authenticated: false, username: null})).toEqual({
      enabled: true,
      authenticated: false,
      username: null,
    });
    expect(parseLoginResponse({token: "token-1", auth: {enabled: true, authenticated: true, username: "admin"}})).toEqual({
      token: "token-1",
      auth: {enabled: true, authenticated: true, username: "admin"},
    });
  });

  it("parses scanner tool config", () => {
    const config = parseToolConfig({
      tools: {
        nmap: {binary_path: "/opt/nmap", timeout_seconds: 60, templates_path: null, default_wordlist: null, extra_args: ["-Pn"]},
        ffuf: {binary_path: null, timeout_seconds: 120, templates_path: null, default_wordlist: "/tmp/words.txt", extra_args: []},
        nuclei: {binary_path: null, timeout_seconds: 180, templates_path: "/tmp/templates", default_wordlist: null, extra_args: []},
      },
    });
    expect(config.tools.nmap.extra_args).toEqual(["-Pn"]);
    expect(config.tools.ffuf.default_wordlist).toBe("/tmp/words.txt");
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

describe("phase 7 DTO parsers", () => {
  it("parses CTF report DTOs", () => {
    expect(parseReport(report).content).toContain("## Overview");
    expect(() => parseReport({...report, metadata: null})).toThrow("Invalid report metadata");
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

const report = {
  id: "report-1",
  public_id: "RPT0001",
  project_id: "project-1",
  session_id: "session-1",
  report_type: "session_writeup",
  title: "Linux target writeup",
  summary: "Linux target writeup",
  material_path: "/tmp/.red-code/projects/project-1/sessions/session-1/reports/report_material.md",
  artifact_path: "/tmp/.red-code/projects/project-1/sessions/session-1/reports/writeup.md",
  created_at: "2026-05-03T00:00:00+00:00",
  metadata: {},
  content: "# Linux target\n\n## Overview\nTODO",
};

const projectReport = {
  ...report,
  id: "report-project-1",
  public_id: "RPT0002",
  session_id: null,
  report_type: "project_writeup",
  title: "HTB Lab project writeup",
};

const session = {
  id: "session-1",
  public_id: "T0001",
  project_id: "project-1",
  name: "Linux target",
  status: "active",
  summary: null,
  created_at: "2026-05-03T00:00:00+00:00",
  updated_at: "2026-05-03T00:00:00+00:00",
  metadata: {},
};

describe("control center DTO parsers", () => {
  it("parses project and session DTOs", () => {
    expect(parseProject(project).public_id).toBe("P0001");
    expect(parseTargetSession(session).name).toBe("Linux target");
  });

  it("parses an empty dashboard DTO", () => {
    const dashboard = parseSessionDashboard({
      project,
      session,
      active_targets: [],
      pending_targets: [],
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

  it("rejects malformed sessions", () => {
    expect(() => parseTargetSession({...session, name: null})).toThrow("Invalid session name");
  });
});

describe("control center API clients", () => {
  it("creates a Project and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({project}));
    vi.stubGlobal("fetch", fetchMock);

    await expect(createProject("http://127.0.0.1:8000", {name: "HTB Lab"})).resolves.toMatchObject({
      id: "project-1",
      name: "HTB Lab",
    });
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/api/projects", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: "HTB Lab"}),
    });
  });

  it("creates a Session and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({session}));
    vi.stubGlobal("fetch", fetchMock);

    await expect(createTargetSession("http://127.0.0.1:8000", "project-1")).resolves.toMatchObject({
      id: "session-1",
      project_id: "project-1",
    });
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/api/projects/project-1/sessions", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({}),
    });
  });

  it("sends an Agent message and parses the queued task", async () => {
    const task = {
      id: "task-1",
      public_id: "TASK0001",
      project_id: "project-1",
      session_id: "session-1",
      task_type: "agent_analysis",
      executor: "ctf_agent",
      status: "pending",
      input: {message: "enumerate target"},
      result: {},
      started_at: null,
      ended_at: null,
      error: null,
      created_at: "2026-05-03T00:00:00+00:00",
      updated_at: "2026-05-03T00:00:00+00:00",
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({task})));

    await expect(
      sendAgentMessage("http://127.0.0.1:8000", "session-1", {message: "enumerate target"}),
    ).resolves.toMatchObject({task_type: "agent_analysis", status: "pending"});
  });

  it("creates a Session writeup report and exposes the download URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({report}));
    vi.stubGlobal("fetch", fetchMock);

    await expect(createSessionReport("http://127.0.0.1:8000", "session-1")).resolves.toMatchObject({
      public_id: "RPT0001",
      report_type: "session_writeup",
    });
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/api/sessions/session-1/reports", {method: "POST"});
    expect(reportDownloadUrl("http://127.0.0.1:8000", "RPT0001")).toBe(
      "http://127.0.0.1:8000/api/reports/RPT0001/download",
    );
  });

  it("lists and creates Project writeup reports", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({reports: [projectReport]}))
      .mockResolvedValueOnce(jsonResponse({report: projectReport}));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listProjectReports("http://127.0.0.1:8000", "project-1")).resolves.toMatchObject([
      {public_id: "RPT0002", session_id: null},
    ]);
    await expect(createProjectReport("http://127.0.0.1:8000", "project-1")).resolves.toMatchObject({
      report_type: "project_writeup",
      session_id: null,
    });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8000/api/projects/project-1/reports", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, "http://127.0.0.1:8000/api/projects/project-1/reports", {method: "POST"});
  });

  it("throws displayable errors for failed API responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("bad", {status: 500})));

    await expect(createProject("http://127.0.0.1:8000", {name: "HTB Lab"})).rejects.toThrow(
      "Request failed: 500",
    );
  });

  it("stores runtime backend URL and auth token", async () => {
    expect(setBackendUrl("http://127.0.0.1:8000/")).toBe("http://127.0.0.1:8000");
    expect(getBackendUrl()).toBe("http://127.0.0.1:8000");

    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      token: "token-1",
      auth: {enabled: true, authenticated: true, username: "admin"},
    }));
    vi.stubGlobal("fetch", fetchMock);

    await login("http://127.0.0.1:8000", {username: "admin", password: "change-me"});
    expect(storage.get(AUTH_TOKEN_STORAGE_KEY)).toBe("token-1");
  });

  it("detects local backend URLs for file opening boundaries", () => {
    expect(isLocalBackendUrl("http://127.0.0.1:8000")).toBe(true);
    expect(isLocalBackendUrl("http://localhost:8000")).toBe(true);
    expect(isLocalBackendUrl("https://control.example.test")).toBe(false);
  });

  it("adds bearer auth and updates tool config", async () => {
    setApiAuthToken("token-1");
    const config = {
      tools: {
        nmap: {binary_path: "/opt/nmap", timeout_seconds: 60, templates_path: null, default_wordlist: null, extra_args: ["-Pn"]},
        ffuf: {binary_path: null, timeout_seconds: 120, templates_path: null, default_wordlist: "/tmp/words.txt", extra_args: []},
        nuclei: {binary_path: null, timeout_seconds: 180, templates_path: "/tmp/templates", default_wordlist: null, extra_args: []},
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({config}))
      .mockResolvedValueOnce(jsonResponse({config}));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getToolConfig("http://127.0.0.1:8000")).resolves.toMatchObject(config);
    await expect(updateToolConfig("http://127.0.0.1:8000", config)).resolves.toMatchObject(config);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/api/tools/config",
      expect.objectContaining({headers: expect.any(Headers)}),
    );
    expect((fetchMock.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer token-1");
  });

  it("includes response detail in failed auth messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({detail: "Authentication required."}), {
      status: 401,
      headers: {"Content-Type": "application/json"},
    })));

    await expect(createProject("http://127.0.0.1:8000", {name: "HTB Lab"})).rejects.toThrow(
      "Request failed: 401 Authentication required.",
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {"Content-Type": "application/json"},
  });
}
