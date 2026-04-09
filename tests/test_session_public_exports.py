import os
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def run_import_probe(script: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(SRC)
        if not existing_pythonpath
        else os.pathsep.join([str(SRC), existing_pythonpath])
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_from_app_import_session_service_avoids_legacy_top_level_imports():
    result = run_import_probe(
        textwrap.dedent(
            """
            import json
            import sys

            from app import SessionService

            legacy_modules = sorted(
                name
                for name in sys.modules
                if name in {
                    "app.operation_service",
                    "app.task_service",
                    "models.operation",
                    "models.task",
                }
            )

            print(json.dumps({"name": SessionService.__name__, "legacy_modules": legacy_modules}))
            """
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '{"name": "SessionService", "legacy_modules": []}'


def test_from_models_import_session_avoids_legacy_top_level_imports():
    result = run_import_probe(
        textwrap.dedent(
            """
            import json
            import sys

            from models import Session

            legacy_modules = sorted(
                name
                for name in sys.modules
                if name in {
                    "models.operation",
                    "models.task",
                }
            )

            print(json.dumps({"name": Session.__name__, "legacy_modules": legacy_modules}))
            """
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '{"name": "Session", "legacy_modules": []}'
