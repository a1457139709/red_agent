import { describe, expect, it } from "vitest";
import { validateProjectForm, validateTargetSessionForm } from "./forms";

describe("validateProjectForm", () => {
  it("requires project name", () => {
    expect(validateProjectForm({name: "  "})).toBe("Project name is required.");
    expect(validateProjectForm({name: "HTB"})).toBeNull();
  });
});

describe("validateTargetSessionForm", () => {
  it("requires session name and target value", () => {
    expect(validateTargetSessionForm({name: "", target_value: "10.10.10.5", target_type: "ip"})).toBe(
      "Session name is required.",
    );
    expect(validateTargetSessionForm({name: "Target", target_value: "", target_type: "ip"})).toBe(
      "Target value is required.",
    );
  });

  it("requires an allowed target type", () => {
    expect(validateTargetSessionForm({name: "Target", target_value: "10.10.10.5", target_type: "bad"})).toBe(
      "Target type is invalid.",
    );
    expect(validateTargetSessionForm({name: "Target", target_value: "10.10.10.5", target_type: "ip"})).toBeNull();
  });
});
