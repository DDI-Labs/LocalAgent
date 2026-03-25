from __future__ import annotations

import json
from pathlib import Path

from .models import AppConfig, BuildingConfig
from .utils import normalize_text_key


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    raw_buildings = payload.get("buildings", [])
    if not isinstance(raw_buildings, list) or not raw_buildings:
        raise ValueError("Config must include a non-empty 'buildings' list.")

    buildings_by_id: dict[str, BuildingConfig] = {}
    alias_lookup: dict[str, str] = {}

    for raw in raw_buildings:
        building_id = str(raw.get("id", "")).strip()
        method = str(raw.get("method", "")).strip().lower()

        if not building_id:
            raise ValueError("Each building must have an 'id'.")
        if method not in {"api", "cua", "openclaw"}:
            raise ValueError(
                f"Building '{building_id}' has invalid method '{method}'. "
                "Expected one of: api, cua, openclaw."
            )

        aliases = raw.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"Building '{building_id}' has invalid 'aliases' format.")

        merged_aliases = [building_id, *[str(a) for a in aliases]]
        building = BuildingConfig(
            id=building_id,
            aliases=merged_aliases,
            method=method,
            raw=raw,
        )
        buildings_by_id[building_id] = building

        for alias in merged_aliases:
            key = normalize_text_key(alias)
            if not key:
                continue
            alias_lookup[key] = building_id

    return AppConfig(buildings_by_id=buildings_by_id, alias_lookup=alias_lookup)

