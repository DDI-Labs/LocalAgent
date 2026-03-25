from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request

from ..models import AdapterResult, BuildingConfig, ParsedPrompt
from ..utils import extract_decision_from_text_or_json, normalize_plate, to_decision


class ApiAdapter:
    def verify(self, building: BuildingConfig, request: ParsedPrompt) -> AdapterResult:
        api_cfg = building.raw.get("api", {})
        mode = str(api_cfg.get("mode", "simulate")).lower()

        if mode == "simulate":
            return self._simulate(building, request, api_cfg)
        if mode == "command":
            return self._command(building, request, api_cfg)
        if mode == "http":
            return self._http(building, request, api_cfg)

        return AdapterResult(
            decision="Denied",
            reason=f"Unsupported API mode '{mode}' for building '{building.id}'.",
        )

    def _simulate(
        self,
        building: BuildingConfig,
        request: ParsedPrompt,
        api_cfg: dict,
    ) -> AdapterResult:
        records = api_cfg.get("simulation_records", {})
        plate = normalize_plate(request.license_plate or "")
        hit = records.get(plate)
        default = to_decision(api_cfg.get("default_decision", False), default="Denied")
        decision = to_decision(hit, default=default)
        return AdapterResult(
            decision=decision,
            reason="API simulation lookup",
            details={
                "plate": plate,
                "record_found": hit is not None,
                "mode": "simulate",
            },
        )

    def _command(
        self,
        building: BuildingConfig,
        request: ParsedPrompt,
        api_cfg: dict,
    ) -> AdapterResult:
        template = api_cfg.get("command")
        if not isinstance(template, list) or not template:
            return AdapterResult(
                decision="Denied",
                reason=f"Building '{building.id}' api.command must be a non-empty list.",
            )

        command = [
            str(part).format(
                building_id=building.id,
                license_plate=request.license_plate or "",
                requester_name=request.requester_name or "",
            )
            for part in template
        ]

        timeout_seconds = int(api_cfg.get("timeout_seconds", 20))
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        decision = extract_decision_from_text_or_json(
            completed.stdout,
            default="Denied" if completed.returncode != 0 else "Accepted",
        )
        return AdapterResult(
            decision=decision,
            reason="API command execution",
            details={
                "mode": "command",
                "return_code": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
        )

    def _http(
        self,
        building: BuildingConfig,
        request: ParsedPrompt,
        api_cfg: dict,
    ) -> AdapterResult:
        endpoint = api_cfg.get("endpoint")
        if not endpoint:
            return AdapterResult(
                decision="Denied",
                reason=f"Building '{building.id}' api.endpoint is required in http mode.",
            )

        method = str(api_cfg.get("http_method", "POST")).upper()
        headers = dict(api_cfg.get("headers", {}))
        headers.setdefault("Content-Type", "application/json")
        timeout_seconds = int(api_cfg.get("timeout_seconds", 20))

        payload = json.dumps(
            {
                "building_id": building.id,
                "requester_name": request.requester_name,
                "license_plate": request.license_plate,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            endpoint, method=method, data=payload if method != "GET" else None, headers=headers
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
            decision = extract_decision_from_text_or_json(body, default="Denied")
            return AdapterResult(
                decision=decision,
                reason="API HTTP call",
                details={"mode": "http", "endpoint": endpoint, "response": body},
            )
        except urllib.error.URLError as exc:
            return AdapterResult(
                decision="Denied",
                reason=f"API HTTP call failed: {exc}",
                details={"mode": "http", "endpoint": endpoint},
            )

