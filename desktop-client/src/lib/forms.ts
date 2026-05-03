import type { TargetType } from "./api";

export const TARGET_TYPE_OPTIONS: TargetType[] = ["ip", "domain", "url", "host", "note"];

export function validateProjectForm(input: { name: string }) {
  return input.name.trim() ? null : "Project name is required.";
}

export function validateTargetSessionForm(input: {
  name: string;
  target_value: string;
  target_type: string;
}) {
  if (!input.name.trim()) {
    return "Session name is required.";
  }
  if (!input.target_value.trim()) {
    return "Target value is required.";
  }
  if (!TARGET_TYPE_OPTIONS.includes(input.target_type as TargetType)) {
    return "Target type is invalid.";
  }
  return null;
}
