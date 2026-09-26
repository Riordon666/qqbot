from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_NAME_CALLS = {"eval", "exec", "compile"}
FORBIDDEN_ATTRIBUTE_CALLS = {
    "system",
    "popen",
    "create_subprocess_exec",
    "create_subprocess_shell",
}
FORBIDDEN_MODULES = {"pty", "subprocess"}


def test_runtime_does_not_offer_remote_code_execution() -> None:
    source_dir = Path(__file__).parents[1] / "src" / "qqbot"
    violations: list[str] = []

    for path in source_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in FORBIDDEN_MODULES:
                        violations.append(f"{path.name}:{node.lineno}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".", 1)[0] in FORBIDDEN_MODULES:
                    violations.append(f"{path.name}:{node.lineno}:from {node.module}")
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAME_CALLS:
                violations.append(f"{path.name}:{node.lineno}:{node.func.id}")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTE_CALLS:
                violations.append(f"{path.name}:{node.lineno}:{node.func.attr}")

    assert violations == []
