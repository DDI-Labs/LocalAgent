from __future__ import annotations

from .adapters.api_adapter import ApiAdapter
from .adapters.cua_adapter import CuaAdapter
from .models import AppConfig, DecisionResult
from .prompt_parser import parse_prompt


class DecisionEngine:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._api_adapter = ApiAdapter()
        self._cua_adapter = CuaAdapter()

    def process_prompt(self, prompt: str) -> DecisionResult:
        parsed = parse_prompt(prompt, self._config.alias_lookup)

        if not parsed.building_id:
            return DecisionResult(
                route="unrouted",
                decision="Denied",
                reason="Could not determine building from prompt.",
                parsed_prompt=parsed.__dict__,
            )

        if not parsed.license_plate:
            return DecisionResult(
                route="unrouted",
                decision="Denied",
                reason="Could not determine license plate from prompt.",
                parsed_prompt=parsed.__dict__,
            )

        building = self._config.buildings_by_id.get(parsed.building_id)
        if not building:
            return DecisionResult(
                route="unrouted",
                decision="Denied",
                reason=f"Building '{parsed.building_id}' not found in config.",
                parsed_prompt=parsed.__dict__,
            )

        if building.method == "openclaw":
            return DecisionResult(
                route="openclaw",
                decision="Delegating to openclaw",
                reason="OpenClaw integration is delegated.",
                parsed_prompt=parsed.__dict__,
                details={"building_id": building.id},
            )

        if building.method == "api":
            outcome = self._api_adapter.verify(building, parsed)
            return DecisionResult(
                route="api",
                decision=outcome.decision,
                reason=outcome.reason,
                parsed_prompt=parsed.__dict__,
                details=outcome.details,
            )

        if building.method == "cua":
            outcome = self._cua_adapter.verify(building, parsed)
            return DecisionResult(
                route="cua",
                decision=outcome.decision,
                reason=outcome.reason,
                parsed_prompt=parsed.__dict__,
                details=outcome.details,
            )

        return DecisionResult(
            route="unrouted",
            decision="Denied",
            reason=f"Unsupported method '{building.method}'.",
            parsed_prompt=parsed.__dict__,
        )

