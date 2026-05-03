import { describe, expect, it } from "vitest";
import { parseHealthResponse } from "./api";

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
