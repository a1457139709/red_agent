import type { TargetType } from "./api";

export const TARGET_TYPE_OPTIONS: TargetType[] = ["ip", "domain", "url", "host", "note"];
export const SCAN_TASK_OPTIONS = ["port_scan", "dir_scan", "poc_scan"] as const;

export function validateProjectForm(input: { name: string }) {
  return input.name.trim() ? null : "Project name is required.";
}

export function validateTargetSessionForm(input: {
  name: string;
}) {
  if (!input.name.trim()) {
    return "Session name is required.";
  }
  return null;
}

export function validateScanTaskForm(input: {
  task_type: string;
  target: string;
  ports?: string;
  wordlist?: string;
}) {
  if (!SCAN_TASK_OPTIONS.includes(input.task_type as (typeof SCAN_TASK_OPTIONS)[number])) {
    return "Scan type is invalid.";
  }
  if (!input.target.trim()) {
    return "Scan target is required.";
  }
  if (input.task_type === "port_scan" && input.ports?.trim()) {
    for (const part of input.ports.split(",")) {
      const port = Number(part.trim());
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        return "Ports must be comma-separated numbers between 1 and 65535.";
      }
    }
  }
  return null;
}

export function validateAgentMessageForm(input: { message: string }) {
  return input.message.trim() ? null : "Agent message is required.";
}
