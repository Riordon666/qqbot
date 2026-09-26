from __future__ import annotations

import ipaddress
import re
import subprocess
from functools import lru_cache
from pathlib import Path


NONEBOT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = (
    NONEBOT_ROOT.parent
    if (NONEBOT_ROOT.parent / "docker-compose.yml").is_file()
    else NONEBOT_ROOT
)

SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".uv-cache",
    ".uv-python",
    "__pycache__",
}
TEXT_FILE_NAMES = {
    ".dockerignore",
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "Dockerfile",
    "LICENSE",
}
TEXT_FILE_SUFFIXES = {
    ".bat",
    ".cfg",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

PRIVATE_FILE_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}
PRIVATE_FILE_NAMES = {
    "id_" + "dsa",
    "id_" + "ecdsa",
    "id_" + "ed25519",
    "id_" + "rsa",
}
RUNTIME_DIRECTORIES = {
    "backups",
    "data/nonebot",
    "napcat/config",
    "napcat/qq",
}
ALLOWED_RUNTIME_MARKERS = {".gitkeep"}

# Generic checks only: never embed private deployment values, even as fragments.
IPV4_PATTERN = re.compile(r"(?<![\w./])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
REMOVED_FEATURE_MARKERS = (
    "fort" + "ress",
    "nar" + "uto",
    "\u8981\u585e",
    "\u4e0d\u826f\u4eba",
)
PRIVATE_KEY_MARKERS = (
    "-" * 5 + "BEGIN OPENSSH PRIVATE KEY" + "-" * 5,
    "-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5,
    "-" * 5 + "BEGIN EC PRIVATE KEY" + "-" * 5,
    "-" * 5 + "BEGIN PRIVATE KEY" + "-" * 5,
)
OBVIOUS_SECRET_PLACEHOLDERS = (
    "change" + "me",
    "change" + "-me",
    "replace" + "-me",
    "replace" + "_me",
    "replace" + "-with-",
    "secret" + "123",
    "password" + "123",
    "your" + "-api-key",
    "your" + "_api_key",
    "your" + "-token",
    "your" + "_token_here",
)
HIGH_CONFIDENCE_SECRET_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])gh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~-]{20,}"),
)
SENSITIVE_EXAMPLE_ASSIGNMENT = re.compile(
    r"^(?P<name>[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)"
    r"[A-Z0-9_]*)\s*=\s*(?P<value>.*)$"
)


def _relative(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


@lru_cache(maxsize=1)
def _release_files() -> tuple[Path, ...]:
    git_directory = REPOSITORY_ROOT / ".git"
    if git_directory.exists():
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, "cannot enumerate Git tracked files"
        paths = [
            REPOSITORY_ROOT / item.decode("utf-8")
            for item in result.stdout.split(b"\0")
            if item
        ]
        return tuple(path for path in paths if path.is_file())

    paths: list[Path] = []
    for path in REPOSITORY_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(REPOSITORY_ROOT).parts
        if any(part in SKIPPED_DIRECTORY_NAMES for part in relative_parts):
            continue
        paths.append(path)
    return tuple(sorted(paths))


def _is_text_file(path: Path) -> bool:
    return path.name in TEXT_FILE_NAMES or path.suffix.lower() in TEXT_FILE_SUFFIXES


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_release_does_not_track_private_or_runtime_files() -> None:
    violations: list[str] = []

    for path in _release_files():
        relative = _relative(path)
        lower_name = path.name.lower()
        lower_relative = relative.lower()

        is_private_environment = lower_name == ".env" or (
            lower_name.startswith(".env.") and not lower_name.endswith(".example")
        )
        if is_private_environment:
            violations.append(f"private environment file: {relative}")
        if any(lower_name.endswith(suffix) for suffix in PRIVATE_FILE_SUFFIXES):
            violations.append(f"private data or key file: {relative}")
        if lower_name in PRIVATE_FILE_NAMES:
            violations.append(f"private identity file: {relative}")

        for directory in RUNTIME_DIRECTORIES:
            prefix = directory + "/"
            if lower_relative.startswith(prefix) and path.name not in ALLOWED_RUNTIME_MARKERS:
                violations.append(f"runtime state file: {relative}")

    assert violations == [], "\n".join(violations)


def test_release_has_no_private_deployment_or_removed_feature_markers() -> None:
    violations: list[str] = []

    for path in _release_files():
        relative = _relative(path)
        lower_relative = relative.casefold()
        if any(marker in lower_relative for marker in REMOVED_FEATURE_MARKERS):
            violations.append(f"removed feature path: {relative}")

        if not _is_text_file(path):
            continue
        content = _text(path)
        folded_content = content.casefold()
        for match in IPV4_PATTERN.finditer(content):
            try:
                address = ipaddress.IPv4Address(match.group())
            except ipaddress.AddressValueError:
                continue
            if address.is_global:
                violations.append(f"public IP literal: {relative}")
        if any(marker in folded_content for marker in REMOVED_FEATURE_MARKERS):
            violations.append(f"removed feature content: {relative}")

    assert violations == [], "\n".join(violations)


def test_release_has_no_high_confidence_secret_material() -> None:
    violations: list[str] = []

    for path in _release_files():
        if not _is_text_file(path):
            continue
        relative = _relative(path)
        content = _text(path)
        folded_content = content.casefold()
        if any(marker in content for marker in PRIVATE_KEY_MARKERS):
            violations.append(f"private key material: {relative}")
        if any(marker in folded_content for marker in OBVIOUS_SECRET_PLACEHOLDERS):
            violations.append(f"unsafe credential placeholder: {relative}")
        if any(pattern.search(content) for pattern in HIGH_CONFIDENCE_SECRET_PATTERNS):
            violations.append(f"credential-shaped value: {relative}")

    assert violations == [], "\n".join(violations)


def test_example_environment_has_no_secret_defaults() -> None:
    example = REPOSITORY_ROOT / ".env.example"
    if not example.is_file():
        return

    violations: list[str] = []
    for line_number, raw_line in enumerate(_text(example).splitlines(), start=1):
        match = SENSITIVE_EXAMPLE_ASSIGNMENT.match(raw_line.strip())
        if match is None:
            continue
        value = match.group("value").strip().strip('"').strip("'")
        if value:
            violations.append(
                f"non-empty secret example default at .env.example:{line_number}"
            )

    assert violations == [], "\n".join(violations)
