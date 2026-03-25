from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BuildingConfig:
    id: str
    aliases: list[str]
    method: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class AppConfig:
    buildings_by_id: dict[str, BuildingConfig]
    alias_lookup: dict[str, str]


@dataclass(frozen=True)
class ParsedPrompt:
    original_prompt: str
    requester_name: str | None
    building_id: str | None
    license_plate: str | None


@dataclass(frozen=True)
class AdapterResult:
    decision: str
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionResult:
    route: str
    decision: str
    reason: str | None
    parsed_prompt: dict[str, Any]
    details: dict[str, Any] = field(default_factory=dict)

