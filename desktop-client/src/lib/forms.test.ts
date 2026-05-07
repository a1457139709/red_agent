import { describe, expect, it } from "vitest";
import { validateAgentMessageForm, validateProjectForm, validateScanTaskForm, validateTargetSessionForm } from "./forms";

describe("validateProjectForm", () => {
  it("requires project name", () => {
    expect(validateProjectForm({name: "  "})).toBe("Project name is required.");
    expect(validateProjectForm({name: "HTB"})).toBeNull();
  });
});

describe("validateScanTaskForm", () => {
  it("validates scan target and scan-specific inputs", () => {
    expect(validateScanTaskForm({task_type: "port_scan", target: "", ports: ""})).toBe("Scan target is required.");
    expect(validateScanTaskForm({task_type: "dir_scan", target: "http://target", wordlist: ""})).toBeNull();
    expect(validateScanTaskForm({task_type: "port_scan", target: "10.10.10.5", ports: "22,bad"})).toBe(
      "Ports must be comma-separated numbers between 1 and 65535.",
    );
    expect(validateScanTaskForm({task_type: "poc_scan", target: "http://target"})).toBeNull();
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

describe("validateAgentMessageForm", () => {
  it("requires a non-empty message", () => {
    expect(validateAgentMessageForm({message: " "})).toBe("Agent message is required.");
    expect(validateAgentMessageForm({message: "枚举这台靶机"})).toBeNull();
  });
});
