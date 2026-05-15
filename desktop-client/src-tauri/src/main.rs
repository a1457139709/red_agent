#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

#[tauri::command]
fn open_report_path(path: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    let canonical = path
        .canonicalize()
        .map_err(|error| format!("Report file not found: {error}"))?;
    validate_report_path(&canonical)?;
    open_path(&canonical)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![open_report_path])
        .run(tauri::generate_context!())
        .expect("failed to run red-code Control Center");
}

fn validate_report_path(path: &Path) -> Result<(), String> {
    let reports_root = env::current_dir()
        .map_err(|error| format!("Could not resolve working directory: {error}"))?
        .canonicalize()
        .map_err(|error| format!("Could not resolve working directory: {error}"))?
        .join(".red-code")
        .join("projects");
    if !path.starts_with(&reports_root) || path.file_name().and_then(|value| value.to_str()) != Some("writeup.md") {
        return Err("Only generated writeup.md files under the app .red-code/projects reports directory may be opened.".to_string());
    }
    let relative = path
        .strip_prefix(&reports_root)
        .map_err(|_| "Report path is outside the app reports directory.".to_string())?;
    if !is_report_artifact_path(relative) {
        return Err("Only generated report artifacts may be opened.".to_string());
    }
    Ok(())
}

fn is_report_artifact_path(relative: &Path) -> bool {
    let parts: Vec<String> = relative
        .components()
        .filter_map(|component| match component {
            Component::Normal(value) => Some(value.to_string_lossy().to_string()),
            _ => None,
        })
        .collect();
    matches!(
        parts.as_slice(),
        [project_id, reports, report_id, file_name]
            if !project_id.is_empty()
                && reports == "reports"
                && report_id.starts_with("RPT")
                && file_name == "writeup.md"
    ) || matches!(
        parts.as_slice(),
        [project_id, sessions, session_id, reports, report_id, file_name]
            if !project_id.is_empty()
                && sessions == "sessions"
                && !session_id.is_empty()
                && reports == "reports"
                && report_id.starts_with("RPT")
                && file_name == "writeup.md"
    )
}

fn open_path(path: &Path) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    let status = Command::new("open").arg(path).status();

    #[cfg(target_os = "windows")]
    let status = Command::new("cmd").args(["/C", "start", ""]).arg(path).status();

    #[cfg(all(unix, not(target_os = "macos")))]
    let status = Command::new("xdg-open").arg(path).status();

    match status {
        Ok(result) if result.success() => Ok(()),
        Ok(result) => Err(format!("Open file command failed with status: {result}")),
        Err(error) => Err(format!("Open file command failed: {error}")),
    }
}
