from __future__ import annotations

import pytest

from qqbot.routing import (
    PluginSpec,
    RouteContext,
    TriggerRegistry,
    can_dispatch,
    normalize_text,
)


async def _handler(_: RouteContext) -> str:
    return "ok"


def _spec(
    plugin_id: str,
    *,
    exact: tuple[str, ...] = (),
    prefixes: tuple[str, ...] = (),
    compact_prefixes: tuple[str, ...] = (),
    fallback: bool = False,
    contexts: frozenset[str] = frozenset({"private", "group"}),
    requires_to_me: bool = False,
) -> PluginSpec:
    return PluginSpec(
        plugin_id=plugin_id,
        name=plugin_id,
        description="test",
        usage=plugin_id,
        handler=_handler,
        exact=exact,
        prefixes=prefixes,
        compact_prefixes=compact_prefixes,
        fallback=fallback,
        contexts=contexts,
        requires_to_me=requires_to_me,
    )


def test_normalization_and_exact_matching() -> None:
    registry = TriggerRegistry()
    registry.register(_spec("ping", exact=("ping",)))
    registry.register(_spec("fallback", fallback=True))
    registry.validate()

    for text in ("ping", " PING ", "ＰＩＮＧ"):
        match = registry.resolve(text)
        assert match is not None
        assert match.spec.plugin_id == "ping"

    assert normalize_text("  Hello   WORLD  ") == "hello world"


def test_exact_is_not_substring_and_falls_back_once() -> None:
    registry = TriggerRegistry()
    registry.register(_spec("ping", exact=("ping",)))
    registry.register(_spec("fallback", fallback=True))

    assert registry.resolve("shopping").spec.plugin_id == "fallback"
    assert registry.resolve("我正在 ping 网站").spec.plugin_id == "fallback"


def test_longest_boundary_prefix_wins() -> None:
    registry = TriggerRegistry()
    registry.register(_spec("short", prefixes=("查询",)))
    registry.register(_spec("long", prefixes=("查询 网站",)))
    registry.register(_spec("fallback", fallback=True))

    match = registry.resolve("查询 网站 订单")
    assert match is not None
    assert match.spec.plugin_id == "long"
    assert match.argument == "订单"
    assert registry.resolve("查询器").spec.plugin_id == "fallback"


def test_longest_compact_prefix_accepts_attached_chinese_argument() -> None:
    registry = TriggerRegistry()
    registry.register(_spec("short", compact_prefixes=("天气",)))
    registry.register(
        _spec("long", compact_prefixes=("天气查询", "查天气"))
    )
    registry.register(_spec("fallback", fallback=True))

    match = registry.resolve("天气查询成都")
    assert match is not None
    assert match.spec.plugin_id == "long"
    assert match.argument == "成都"

    match = registry.resolve("查天气上海")
    assert match is not None
    assert match.spec.plugin_id == "long"
    assert match.argument == "上海"

    match = registry.resolve("天气查询：北京")
    assert match is not None
    assert match.spec.plugin_id == "long"
    assert match.argument == "北京"


def test_boundary_prefix_still_rejects_attached_text() -> None:
    registry = TriggerRegistry()
    registry.register(_spec("query", prefixes=("查询",)))
    registry.register(_spec("fallback", fallback=True))

    assert registry.resolve("查询器").spec.plugin_id == "fallback"
    assert registry.resolve("查询 内容").spec.plugin_id == "query"


def test_registration_conflicts_fail_fast() -> None:
    registry = TriggerRegistry()
    registry.register(_spec("one", exact=("help",)))
    with pytest.raises(ValueError, match="Duplicate exact alias"):
        registry.register(_spec("two", exact=(" HELP ",)))

    registry = TriggerRegistry()
    registry.register(_spec("fallback-one", fallback=True))
    with pytest.raises(ValueError, match="Multiple fallback"):
        registry.register(_spec("fallback-two", fallback=True))


@pytest.mark.parametrize(
    ("first_kind", "second_kind"),
    (("prefixes", "compact_prefixes"), ("compact_prefixes", "prefixes")),
)
def test_prefix_conflicts_span_boundary_and_compact_kinds(
    first_kind: str,
    second_kind: str,
) -> None:
    registry = TriggerRegistry()
    registry.register(_spec("one", **{first_kind: ("天气查询",)}))

    with pytest.raises(ValueError, match="Duplicate prefix alias"):
        registry.register(_spec("two", **{second_kind: (" 天气查询 ",)}))


def test_fallback_cannot_declare_compact_prefixes() -> None:
    registry = TriggerRegistry()

    with pytest.raises(ValueError, match="Fallback plugin cannot declare"):
        registry.register(
            _spec(
                "fallback",
                compact_prefixes=("天气查询",),
                fallback=True,
            )
        )


def test_context_gate_keeps_explicit_match_from_falling_back() -> None:
    registry = TriggerRegistry()
    registry.register(
        _spec(
            "private-only",
            exact=("private command",),
            contexts=frozenset({"private"}),
        )
    )
    registry.register(_spec("fallback", fallback=True))

    match = registry.resolve("private command")
    assert match is not None
    assert match.spec.plugin_id == "private-only"
    assert can_dispatch(match.spec, "private", to_me=False)
    assert not can_dispatch(match.spec, "group", to_me=True)
    assert match.spec.plugin_id != "fallback"


def test_requires_to_me_only_gates_group_messages() -> None:
    spec = _spec(
        "mentioned",
        exact=("mentioned",),
        requires_to_me=True,
    )

    assert not can_dispatch(spec, "group", to_me=False)
    assert can_dispatch(spec, "group", to_me=True)
    assert can_dispatch(spec, "private", to_me=False)


def test_default_plugins_keep_existing_group_behavior_without_mention() -> None:
    spec = _spec("ping", exact=("ping",))

    assert spec.requires_to_me is False
    assert can_dispatch(spec, "group", to_me=False)
