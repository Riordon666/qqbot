from __future__ import annotations

import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from nonebot import logger


_SKILL_ID_RE = re.compile(r"[a-z0-9_]{1,64}")
_MAX_SKILL_FILE_BYTES = 32 * 1024


@dataclass(frozen=True, slots=True)
class LocalSkill:
    skill_id: str
    name: str
    description: str
    triggers: tuple[str, ...]
    contexts: frozenset[str]
    always: bool
    instructions: str


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().casefold()


class LocalSkillRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._skills: tuple[LocalSkill, ...] = ()
        self.reload()

    @property
    def skills(self) -> tuple[LocalSkill, ...]:
        return self._skills

    def reload(self) -> None:
        loaded: list[LocalSkill] = []
        if not self.root.exists():
            logger.warning("Local Skill directory does not exist: {}", self.root)
            self._skills = ()
            return
        if self.root.is_symlink() or not self.root.is_dir():
            logger.warning("Local Skill path is not a safe directory")
            self._skills = ()
            return

        for directory in sorted(self.root.iterdir(), key=lambda path: path.name):
            if directory.name.startswith(".") or not directory.is_dir():
                continue
            try:
                loaded.append(self._load_one(directory))
            except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError) as exc:
                logger.warning(
                    "Skipped invalid local Skill {}: {}",
                    directory.name,
                    type(exc).__name__,
                )
        self._skills = tuple(skill for skill in loaded if skill is not None)
        logger.info("Loaded {} local chat Skill(s)", len(self._skills))

    def _load_one(self, directory: Path) -> LocalSkill:
        if directory.is_symlink():
            raise ValueError("Skill directory cannot be a symlink")
        manifest_path = directory / "skill.toml"
        instructions_path = directory / "SKILL.md"
        if not manifest_path.is_file() or not instructions_path.is_file():
            raise ValueError("Skill requires skill.toml and SKILL.md")
        if manifest_path.is_symlink() or instructions_path.is_symlink():
            raise ValueError("Skill files cannot be symlinks")
        if instructions_path.stat().st_size > _MAX_SKILL_FILE_BYTES:
            raise ValueError("SKILL.md is too large")

        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        skill_id = str(manifest.get("id", "")).strip()
        if not _SKILL_ID_RE.fullmatch(skill_id) or skill_id != directory.name:
            raise ValueError("Skill id must match its directory")
        if manifest.get("enabled", True) is not True:
            raise ValueError("Skill is disabled")

        name = str(manifest.get("name", "")).strip()
        description = str(manifest.get("description", "")).strip()
        if not name or not description:
            raise ValueError("Skill name and description are required")

        raw_triggers = manifest.get("triggers", [])
        if not isinstance(raw_triggers, list) or not all(
            isinstance(item, str) and item.strip() for item in raw_triggers
        ):
            raise ValueError("Skill triggers must be a list of strings")
        triggers = tuple(_normalize(item) for item in raw_triggers)

        raw_contexts = manifest.get("contexts", ["private", "group"])
        if not isinstance(raw_contexts, list):
            raise ValueError("Skill contexts must be a list")
        contexts = frozenset(str(item) for item in raw_contexts)
        if not contexts or not contexts <= {"private", "group"}:
            raise ValueError("Skill contexts are invalid")

        always = manifest.get("always", False)
        if not isinstance(always, bool):
            raise ValueError("Skill always must be a boolean")
        instructions = instructions_path.read_text(encoding="utf-8").strip()
        if not instructions:
            raise ValueError("SKILL.md cannot be empty")

        return LocalSkill(
            skill_id=skill_id,
            name=name,
            description=description,
            triggers=triggers,
            contexts=contexts,
            always=always,
            instructions=instructions,
        )

    def render_for_message(
        self,
        text: str,
        context_kind: str,
        max_total_chars: int,
    ) -> str:
        normalized = _normalize(text)
        sections: list[str] = []
        used = 0
        for skill in self._skills:
            if context_kind not in skill.contexts:
                continue
            if not skill.always and not any(
                trigger in normalized for trigger in skill.triggers
            ):
                continue
            section = (
                f"### 本地 Skill：{skill.name} ({skill.skill_id})\n"
                f"用途：{skill.description}\n"
                f"{skill.instructions}"
            )
            remaining = max_total_chars - used
            if remaining <= 0:
                break
            if len(section) > remaining:
                section = section[:remaining].rstrip() + "…"
            sections.append(section)
            used += len(section)
        return "\n\n".join(sections)
