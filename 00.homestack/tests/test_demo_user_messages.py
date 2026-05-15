"""Smoke tests for rich formatter demo scripts."""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_demo_user_messages_importable_without_running_main() -> None:
    script_path = _project_root() / "scripts" / "demo_user_messages.py"

    spec = spec_from_file_location("demo_user_messages", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "main")


def test_demo_user_messages_executes_successfully() -> None:
    project_root = _project_root()
    script_path = project_root / "scripts" / "demo_user_messages.py"

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{project_root / 'src'}:{env['PYTHONPATH']}"
        if "PYTHONPATH" in env and env["PYTHONPATH"]
        else str(project_root / "src")
    )

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "WELCOME" in result.stdout
    assert "SUCCESS SUMMARY" in result.stdout
