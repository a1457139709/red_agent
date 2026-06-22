import { describe, expect, it } from "vitest";
import { validateAgentMessageForm, validateProjectForm, validateScanTaskForm } from "./forms";

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

describe("validateAgentMessageForm", () => {
  it("requires a non-empty message", () => {
    expect(validateAgentMessageForm({message: " "})).toBe("Agent message is required.");
    expect(validateAgentMessageForm({message: "枚举这台靶机"})).toBeNull();
  });
});
