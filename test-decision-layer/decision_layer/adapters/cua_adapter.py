from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from typing import Any

from ..models import AdapterResult, BuildingConfig, ParsedPrompt
from ..utils import extract_decision_from_text_or_json, normalize_plate, to_decision


class CuaAdapter:
    def verify(self, building: BuildingConfig, request: ParsedPrompt) -> AdapterResult:
        cua_cfg = building.raw.get("cua", {})
        mode = str(cua_cfg.get("mode", "simulate")).lower()
        handoff = self._build_handoff_payload(building, request, cua_cfg)

        if mode == "simulate":
            result = self._simulate(request, cua_cfg)
            return AdapterResult(
                decision=result.decision,
                reason="CUA simulation",
                details={**result.details, "handoff": handoff, "mode": "simulate"},
            )
        if mode == "command":
            result = self._command(handoff, cua_cfg)
            return AdapterResult(
                decision=result.decision,
                reason="CUA command execution",
                details={**result.details, "handoff": handoff, "mode": "command"},
            )
        if mode == "http":
            result = self._http(handoff, cua_cfg)
            return AdapterResult(
                decision=result.decision,
                reason="CUA HTTP execution",
                details={**result.details, "handoff": handoff, "mode": "http"},
            )

        return AdapterResult(
            decision="Denied",
            reason=f"Unsupported CUA mode '{mode}' for building '{building.id}'.",
            details={"handoff": handoff},
        )

    def _build_handoff_payload(
        self,
        building: BuildingConfig,
        request: ParsedPrompt,
        cua_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "building_id": building.id,
            "remote_connection_app": cua_cfg.get("remote_connection_app"),
            "remote_host": cua_cfg.get("remote_host"),
            "credentials": cua_cfg.get("credentials", {}),
            "remote_verification_app": cua_cfg.get("remote_verification_app"),
            "verification_steps": cua_cfg.get("verification_steps", []),
            "claimant": {
                "name": request.requester_name,
                "license_plate": request.license_plate,
            },
        }

    def _simulate(self, request: ParsedPrompt, cua_cfg: dict[str, Any]) -> AdapterResult:
        records = cua_cfg.get("simulation_records", {})
        plate = normalize_plate(request.license_plate or "")
        hit = records.get(plate)
        default = to_decision(cua_cfg.get("default_decision", False), default="Denied")
        decision = to_decision(hit, default=default)
        return AdapterResult(
            decision=decision,
            details={"plate": plate, "record_found": hit is not None},
        )

    def _command(self, handoff: dict[str, Any], cua_cfg: dict[str, Any]) -> AdapterResult:
        template = cua_cfg.get("command")
        if not isinstance(template, list) or not template:
            return AdapterResult(
                decision="Denied",
                reason="cua.command must be a non-empty list in command mode.",
            )

        command = [str(item) for item in template]
        timeout_seconds = int(cua_cfg.get("timeout_seconds", 40))
        pass_payload = bool(cua_cfg.get("pass_payload_via_stdin", True))

        completed = subprocess.run(
            command,
            input=json.dumps(handoff) if pass_payload else None,
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
            details={
                "return_code": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
        )

    def _http(self, handoff: dict[str, Any], cua_cfg: dict[str, Any]) -> AdapterResult:
        endpoint = cua_cfg.get("endpoint")
        if not endpoint:
            return AdapterResult(
                decision="Denied",
                reason="cua.endpoint is required in http mode.",
            )

        method = str(cua_cfg.get("http_method", "POST")).upper()
        headers = dict(cua_cfg.get("headers", {}))
        headers.setdefault("Content-Type", "application/json")
        timeout_seconds = int(cua_cfg.get("timeout_seconds", 40))

        payload = json.dumps(handoff).encode("utf-8")
        req = urllib.request.Request(
            endpoint, method=method, data=payload if method != "GET" else None, headers=headers
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
            decision = extract_decision_from_text_or_json(body, default="Denied")
            return AdapterResult(decision=decision, details={"response": body, "endpoint": endpoint})
        except urllib.error.URLError as exc:
            return AdapterResult(
                decision="Denied",
                reason=f"CUA HTTP call failed: {exc}",
                details={"endpoint": endpoint},
            )

