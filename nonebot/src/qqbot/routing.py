from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from nonebot.adapters.onebot.v11 import MessageEvent


RouteHandler = Callable[["RouteContext"], Awaitable[str | None]]
ContextKind = Literal["private", "group"]


@dataclass(frozen=True, slots=True)
class RouteContext:
    event: MessageEvent
    text: str
    normalized_text: str
    argument: str
    qq_id: str
    nickname: str
    group_card: str | None
    conversation_key: str
    conversation_kind: ContextKind
    scope_id: str
    source_message_id: str


@dataclass(frozen=True, slots=True)
class PluginSpec:
    plugin_id: str
    name: str
    description: str
    usage: str
    handler: RouteHandler
    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    compact_prefixes: tuple[str, ...] = ()
    category: str = "基础"
    order: int = 100
    admin_only: bool = False
    hidden: bool = False
    fallback: bool = False
    contexts: frozenset[ContextKind] = frozenset({"private", "group"})
    requires_to_me: bool = False


@dataclass(frozen=True, slots=True)
class RouteMatch:
    spec: PluginSpec
    text: str
    normalized_text: str
    argument: str


def can_dispatch(
    spec: PluginSpec,
    context_kind: ContextKind,
    *,
    to_me: bool,
) -> bool:
    if context_kind not in spec.contexts:
        return False
    if context_kind == "group" and spec.requires_to_me and not to_me:
        return False
    return True


_WHITESPACE_RE = re.compile(r"\s+")


def prepare_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", text).strip())


def normalize_text(text: str) -> str:
    return prepare_text(text).casefold()


class TriggerRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, PluginSpec] = {}
        self._exact: dict[str, PluginSpec] = {}
        self._prefixes: list[tuple[str, PluginSpec, bool]] = []
        self._fallback: PluginSpec | None = None

    def register(self, spec: PluginSpec) -> None:
        if not re.fullmatch(r"[a-z0-9_.-]{1,64}", spec.plugin_id):
            raise ValueError(f"Invalid plugin id: {spec.plugin_id!r}")
        if spec.plugin_id in self._specs:
            raise ValueError(f"Duplicate plugin id: {spec.plugin_id}")
        if not spec.contexts or not spec.contexts <= {"private", "group"}:
            raise ValueError(f"Invalid contexts for plugin: {spec.plugin_id}")
        if spec.fallback:
            if self._fallback is not None:
                raise ValueError(
                    f"Multiple fallback plugins: {self._fallback.plugin_id}, "
                    f"{spec.plugin_id}"
                )
            if spec.exact or spec.prefixes or spec.compact_prefixes:
                raise ValueError("Fallback plugin cannot declare keyword triggers")
            self._fallback = spec
        elif not spec.exact and not spec.prefixes and not spec.compact_prefixes:
            raise ValueError(f"Plugin has no trigger: {spec.plugin_id}")

        for alias in spec.exact:
            normalized = normalize_text(alias)
            if not normalized:
                raise ValueError(f"Empty exact alias in plugin: {spec.plugin_id}")
            previous = self._exact.get(normalized)
            if previous is not None:
                raise ValueError(
                    f"Duplicate exact alias {alias!r}: "
                    f"{previous.plugin_id}, {spec.plugin_id}"
                )
            self._exact[normalized] = spec

        existing_prefixes = {
            alias: owner for alias, owner, _ in self._prefixes
        }
        for aliases, allow_compact in (
            (spec.prefixes, False),
            (spec.compact_prefixes, True),
        ):
            for alias in aliases:
                normalized = normalize_text(alias)
                if not normalized:
                    raise ValueError(
                        f"Empty prefix alias in plugin: {spec.plugin_id}"
                    )
                previous = existing_prefixes.get(normalized)
                if previous is not None:
                    raise ValueError(
                        f"Duplicate prefix alias {alias!r}: "
                        f"{previous.plugin_id}, {spec.plugin_id}"
                    )
                self._prefixes.append((normalized, spec, allow_compact))
                existing_prefixes[normalized] = spec

        self._prefixes.sort(
            key=lambda item: (-len(item[0]), item[1].order, item[1].plugin_id)
        )
        self._specs[spec.plugin_id] = spec

    def validate(self) -> None:
        if self._fallback is None:
            raise ValueError("Exactly one fallback plugin is required")

    def resolve(self, text: str, include_fallback: bool = True) -> RouteMatch | None:
        prepared = prepare_text(text)
        normalized = prepared.casefold()
        if not normalized:
            return None

        if spec := self._exact.get(normalized):
            return RouteMatch(spec, prepared, normalized, "")

        for prefix, spec, allow_compact in self._prefixes:
            if not normalized.startswith(prefix):
                continue
            suffix = normalized[len(prefix) :]
            if (
                suffix
                and not allow_compact
                and suffix[0] not in {" ", ":", "："}
            ):
                continue
            argument = prepared[len(prefix) :].lstrip(" :：")
            return RouteMatch(spec, prepared, normalized, argument)

        if include_fallback and self._fallback is not None:
            return RouteMatch(self._fallback, prepared, normalized, prepared)
        return None

    def specs(self) -> tuple[PluginSpec, ...]:
        return tuple(
            sorted(
                self._specs.values(),
                key=lambda spec: (spec.category, spec.order, spec.plugin_id),
            )
        )


registry = TriggerRegistry()
