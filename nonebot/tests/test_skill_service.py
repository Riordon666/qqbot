from __future__ import annotations

from pathlib import Path

from qqbot.services.skill_service import LocalSkillRegistry


def _write_skill(
    root: Path,
    skill_id: str,
    *,
    always: bool,
    triggers: list[str],
) -> None:
    directory = root / skill_id
    directory.mkdir()
    directory.joinpath("skill.toml").write_text(
        "\n".join(
            [
                f'id = "{skill_id}"',
                f'name = "{skill_id}"',
                'description = "test skill"',
                "enabled = true",
                f"always = {str(always).lower()}",
                f"triggers = {triggers!r}".replace("'", '"'),
                'contexts = ["private", "group"]',
            ]
        ),
        encoding="utf-8",
    )
    directory.joinpath("SKILL.md").write_text(
        f"# {skill_id}\n\nFollow this local instruction.",
        encoding="utf-8",
    )


def test_prompt_only_local_skills_are_selected_by_context_and_trigger(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "always_chat", always=True, triggers=[])
    _write_skill(
        tmp_path,
        "website_query",
        always=False,
        triggers=["查询网站"],
    )

    registry = LocalSkillRegistry(tmp_path)
    assert {skill.skill_id for skill in registry.skills} == {
        "always_chat",
        "website_query",
    }

    ordinary = registry.render_for_message("你好", "private", 5000)
    assert "always_chat" in ordinary
    assert "website_query" not in ordinary

    website = registry.render_for_message("帮我查询网站信息", "private", 5000)
    assert "always_chat" in website
    assert "website_query" in website


def test_invalid_skill_isolated_from_valid_skill(tmp_path: Path) -> None:
    _write_skill(tmp_path, "valid_skill", always=True, triggers=[])
    invalid = tmp_path / "wrong_directory"
    invalid.mkdir()
    invalid.joinpath("skill.toml").write_text(
        'id = "different_id"\nname = "bad"\ndescription = "bad"',
        encoding="utf-8",
    )
    invalid.joinpath("SKILL.md").write_text("bad", encoding="utf-8")

    registry = LocalSkillRegistry(tmp_path)
    assert [skill.skill_id for skill in registry.skills] == ["valid_skill"]
