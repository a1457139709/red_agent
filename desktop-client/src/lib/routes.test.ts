import { describe, expect, it } from "vitest";
import { parseWorkspaceHash, projectHash, sessionHash } from "./routes";

describe("workspace routes", () => {
  it("parses empty, project, and session hashes", () => {
    expect(parseWorkspaceHash("")).toEqual({projectId: null, sessionId: null});
    expect(parseWorkspaceHash("#/projects/P0001")).toEqual({projectId: "P0001", sessionId: null});
    expect(parseWorkspaceHash("#/projects/P0001/sessions/T0001")).toEqual({
      projectId: "P0001",
      sessionId: "T0001",
    });
  });

  it("builds project and session hashes", () => {
    expect(projectHash("project-1")).toBe("#/projects/project-1");
    expect(sessionHash("project-1", "session-1")).toBe("#/projects/project-1/sessions/session-1");
  });
});
