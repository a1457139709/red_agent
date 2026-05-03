# red-code

`red-code` is a local Python CLI agent for coding work and bounded red-team style inspection. It combines a LangChain/OpenAI-compatible tool loop with persistent session state, capability manifests, typed security tools, and a session-owned artifact/report store.

The project is designed for local single-user development workflows. It is not a hosted agent platform or a multi-user service.

## Overview

`red-code` has two primary modes:

- Normal mode: ask coding, repository, file, shell, and web-research questions through a local CLI agent.
- Redteam mode: use AI-assisted automated testing and run scoped reconnaissance workflows through typed tools, admission checks, persisted jobs, artifacts, findings, reports, and dashboards.

The runtime is session-first. User-facing records are organized around `Session`, `Run`, `Job`, `Artifact`, `Finding`, `Report`, `MemoryEntry`, and `SessionEvent`.

## What It Is For

Use this project when you want a local assistant that can:

- inspect and edit a repository through controlled file tools
- run shell commands with safety checks
- keep persistent session history, logs, checkpoints, and reports
- activate prompt-assist skills for focused workflows
- run capability-backed modules such as `surface-recon` and `web-enum`
- execute bounded DNS, HTTP, TLS, banner, and TCP port-scan checks inside a scoped redteam session
- persist raw tool output as artifacts and connect those artifacts to findings and reports

## Core Features

- Interactive Rich-based CLI with slash-command completion and persistent input history.
- Natural-language first controller flow with slash commands for advanced control.
- OpenAI-compatible model configuration through environment variables.
- Factory-defined tool execution for file, shell, web, and session-facing security tools, with LangChain adapters generated at the boundary.
- Capability manifests for prompt-assist skills and executable modules.
- Session persistence through SQLite plus file-backed checkpoint and artifact storage.
- Redteam sessions with scope policies, admission checks, confirmation gates, job leases, retries, and cooperative cancellation.
- Structured artifacts, findings, reports, dashboards, and planner proposals.
- Web-ready DTO and interaction adapter contracts under `src/web/`.

## Installation

Requirements:

- Python 3.12 or newer
- An OpenAI-compatible chat model endpoint

Create a virtual environment:

```bash
# macOS / Linux
python3.12 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

```powershell
# Windows PowerShell
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If you only want runtime dependencies, you can also install from `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

## Configuration

Configuration is read from the environment. A local `.env` file is supported.

Minimum required settings:

```env
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=your-model-name
```

Common optional settings:

```env
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_REASONING_EFFORT=medium
MODEL_TEMPERATURE=0.5
MAX_AGENT_STEPS=50
MODEL_CONTEXT_TOKEN_LIMIT=128000
COMPRESSION_THRESHOLD=0.8
SYSTEM_PROMPT_RESERVE=2000
```

`OPENAI_API_BASE` is optional for providers that work with the default OpenAI client settings. Set it when using a compatible gateway or local proxy.

## Running the CLI

Start the CLI from the repository root:

```bash
venv/bin/python src/main.py
```

```powershell
venv\Scripts\python src\main.py
```

Startup prints an ASCII banner and a short command guide:

```text
 ____  _____ ____        ____ ___  ____  _____
|  _ \| ____|  _ \      / ___/ _ \|  _ \| ____|
| |_) |  _| | | | |____| |  | | | | | | |  _|
|  _ <| |___| |_| |____| |__| |_| | |_| | |___
|_| \_\_____|____/      \____\___/|____/|_____|

RED-CODE 0.1.0
Command-driven local agent for development and bounded redteam workflows.
Use /help for commands.
Use /redteam to enter redteam mode, /normal to return.
Redteam mode: use AI-assisted automated testing, run scoped modules, then inspect findings, artifacts, and reports.
```

The prompt shows the current mode and active session when one is bound. The CLI is command-driven; use `/help` to list available commands. The interactive prompt supports `/` command completion, dynamic completion for sessions/resources/skills/modules, arrow-key history navigation, and a workspace-local history file at `.red-code/history`.

TTY controls:

- `Tab`: complete slash commands, subcommands, and known ids when available.
- `Up` / `Down`: move through persisted command history.
- `Ctrl-C`: ask whether to exit; answer `y` or `yes` to leave the shell.
- `Ctrl-D`: exit the shell.

Examples:

```text
/help
/redteam
/module run surface-recon example.com {"include_tls": true}
/findings latest
/normal
```

## Command Reference

Use `/help` inside the CLI for the live command guide.

General commands:

- `/help`
- `/help findings`
- `/help artifacts`
- `/help reports`
- `/help skill`
- `/help module`
- `/clear`
- `/reset`
- `/exit`
- `/quit`

Session and record lookup:

- `/status [current|latest|S0001]`
- `/history [current|latest|S0001]`
- `/steps [current|latest|S0001]`
- `/artifacts [current|latest|S0001]`
- `/findings [current|latest|S0001]`
- `/reports [current|latest|S0001]`
- `/show <public_id> [current|latest|S0001]`
- `/why <finding_public_id> [current|latest|S0001]`

Redteam mode:

- `/redteam`
- `/normal`

Artifacts, findings, reports, and dashboards:

- `/artifacts list [current|latest|S0001] [limit]`
- `/artifacts show <artifact_id>`
- `/findings list [current|latest|S0001] [limit]`
- `/findings show <finding_id>`
- `/findings confirm <finding_id>`
- `/findings dismiss <finding_id>`
- `/reports generate <session_summary|findings_summary|operator_report> [current|latest|S0001]`
- `/reports list [current|latest|S0001] [limit]`
- `/reports show <report_id>`
- `/dashboard`
- `/dashboard <session_id>`

Planner:

- `/planner plan <session_id>`
- `/planner apply <plan_id> [1,3,...]`

Skills:

- `/skill list`
- `/skill show <name>`
- `/skill use <name>`
- `/skill reload`
- `/skill clear`
- `/skill current`
- `/skill help`
- `/skill-name <prompt>`

Modules:

- `/module list`
- `/module show <name>`
- `/module run <name> <target> [json_overrides]`

## Control Center Development

Phase 1 adds a local App Server and a desktop shell for the CTF Control Center direction.

Start the backend from the repository root:

```bash
.venv/bin/python -m uvicorn server.app:create_app --factory --reload
```

Start the desktop shell:

```bash
cd desktop-client
npm install
npm run dev
```

Run the Tauri desktop app when Rust/Cargo is installed:

```bash
cd desktop-client
npm run tauri dev
```

The desktop shell defaults to `http://127.0.0.1:8000` and can be pointed at another backend with `VITE_BACKEND_URL`.

## Usage Examples

Activate a prompt-assist skill:

```text
/skill list
/skill use security-audit
```

Run a one-shot skill without changing the active shell skill:

```text
/security-audit Review src/app/session_service.py
```

Switch into redteam mode:

```text
/redteam
```

Run a built-in module:

```text
/module list
/module show surface-recon
/module run surface-recon example.com {"include_tls": true}
```

Inspect records from the active or latest session:

```text
/status latest
/artifacts latest
/findings latest
/show A0001 latest
/why F0001 latest
```

When there is no active session, record lookup commands require an explicit scope such as `latest` or `S0001`.

Generate and inspect reports:

```text
/reports generate session_summary latest
/reports generate findings_summary latest
/reports generate operator_report latest
/reports latest
/reports show R0001
```

Create and apply planner proposals:

```text
/planner plan S0001
/planner apply PLN0001
/planner apply PLN0001 1,3
```

## Storage Layout

Runtime state is stored under `.red-code/` in the current working directory.

```text
.red-code/
  agent.db
  config/
    risk-policy.json
  capabilities/
  sessions/
    <session_id>/
      memory/
        checkpoints/
          YYYY/
            MM/
              chk_<checkpoint_id>.json.gz
      artifacts/
      findings/
      reports/
```

SQLite stores structured metadata and relationships. Larger checkpoint and artifact payloads are stored as files under the owning session directory. Public IDs such as `S0001`, `A0001`, `F0001`, and `R0001` are for CLI display and lookup; internal storage uses stable session IDs.

## Capabilities and Modules

Skills and modules are both loaded as capabilities. The registry scans capability roots for directories that contain a `capability.json` manifest.

Built-in capabilities live under:

```text
src/capabilities/
```

User-local capabilities live under:

```text
.red-code/capabilities/
```

Loading order:

- Built-in capabilities are loaded first from `src/capabilities/`.
- User-local capabilities are loaded second from `.red-code/capabilities/`.
- If a local capability uses the same `name` and directory name as a built-in capability, the local capability overrides the built-in one.
- The loaded capability list is cached for the running CLI process.
- Use `/skill reload` to clear the cache and rescan capability directories after adding or editing local capabilities.

Each capability directory must be named exactly the same as the manifest `name` field. For example, a skill with `"name": "my-skill"` must live in a directory named `my-skill`.

A prompt-assist skill is a capability with `"kind": "skill"`. It must contain both `capability.json` and a non-empty `prompt.md` file:

```text
.red-code/
  capabilities/
    my-skill/
      capability.json
      prompt.md
```

An executable module is a capability with `"kind": "module"`. It uses `capability.json` only and declares workflow execution metadata:

```text
.red-code/
  capabilities/
    my-module/
      capability.json
```

Minimal local skill example:

```json
{
  "version": 1,
  "name": "my-skill",
  "kind": "skill",
  "display_name": "My Skill",
  "description": "A local prompt-assist skill.",
  "modes": ["normal"],
  "parameters": [],
  "tools": {
    "allowed": ["read_file", "search"]
  },
  "risk": {
    "default": "safe",
    "actions": []
  },
  "execution": {
    "style": "prompt_assist",
    "profile": "my-skill"
  },
  "session": {
    "supports_one_shot": true,
    "supports_persistent": true,
    "result_layers": []
  }
}
```

Optional capability folders:

- `references/`: static files that belong to the capability.
- `scripts/`: helper scripts shipped with the capability.

The loader records files from these folders so services can expose them with the loaded capability metadata. The loader does not recursively scan nested directories inside `references/` or `scripts/`.

Built-in prompt-assist skills:

- `development-default`
- `git-auto-commit`
- `security-audit`
- `weather-query-example`

Built-in executable modules:

- `surface-recon`
- `web-enum`

## Development and Tests

Run the test suite:

```bash
venv/bin/python -m pytest
```

```powershell
venv\Scripts\python -m pytest
```

Useful focused checks:

```bash
venv/bin/python -m pytest tests/test_session_public_exports.py tests/test_module_service.py tests/test_capability_service.py
```

## Project Structure

Core source areas:

- `src/main.py`: CLI entrypoint and command routing
- `src/agent/`: model loop, prompt, context, settings, and local agent state
- `src/controller/`: natural-language controller contracts and routing helpers
- `src/app/`: application services for sessions, execution, reports, records, and capabilities
- `src/models/`: domain models
- `src/orchestration/`: admission, scope validation, scheduler, worker-facing job orchestration, and planner runtime
- `src/runtime/`: execution runtime, worker runtime, leases, isolation, and timeouts
- `src/storage/`: SQLite repositories and file path helpers
- `src/tools/`: factory-defined file, shell, web, and typed security tools plus structured execution events
- `src/capabilities/`: built-in skill and module manifests
- `src/web/`: transport-neutral DTOs and interaction adapter contracts
- `docs/`: maintained architecture and development documentation
