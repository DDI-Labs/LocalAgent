from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
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
        context = {
            "building_id": building.id,
            "requester_name": request.requester_name or "",
            "license_plate": request.license_plate or "",
        }

        endpoint = self._resolve_endpoint(api_cfg, context)
        if not endpoint:
            return AdapterResult(
                decision="Denied",
                reason=f"Building '{building.id}' api.endpoint or api.endpoint_template is required in http mode.",
            )

        method = str(api_cfg.get("http_method", "POST")).upper()
        headers = dict(api_cfg.get("headers", {}))
        decision_field = api_cfg.get("decision_field")
        timeout_seconds = int(api_cfg.get("timeout_seconds", 20))
        query_params = api_cfg.get("query_params", {})

        if isinstance(query_params, dict) and query_params:
            endpoint = self._append_query_params(endpoint, query_params, context)

        payload = None
        if method != "GET":
            headers.setdefault("Content-Type", "application/json")
            payload_template = api_cfg.get("request_payload")
            payload_object = (
                self._format_mapping(payload_template, context)
                if isinstance(payload_template, dict)
                else {
                    "building_id": building.id,
                    "requester_name": request.requester_name,
                    "license_plate": request.license_plate,
                }
            )
            payload = json.dumps(payload_object).encode("utf-8")

        req = urllib.request.Request(
            endpoint, method=method, data=payload, headers=headers
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = int(getattr(response, "status", 200))

            decision = self._decision_from_response(body, decision_field)
            return AdapterResult(
                decision=decision,
                reason="API HTTP call",
                details={
                    "mode": "http",
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "response": body,
                },
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return AdapterResult(
                decision="Denied",
                reason=f"API HTTP error: {exc.code}",
                details={
                    "mode": "http",
                    "endpoint": endpoint,
                    "status_code": int(exc.code),
                    "response": body,
                },
            )
        except urllib.error.URLError as exc:
            return AdapterResult(
                decision="Denied",
                reason=f"API HTTP call failed: {exc}",
                details={"mode": "http", "endpoint": endpoint},
            )

    @staticmethod
    def _resolve_endpoint(api_cfg: dict, context: dict[str, str]) -> str:
        endpoint_template = api_cfg.get("endpoint_template")
        if isinstance(endpoint_template, str) and endpoint_template.strip():
            return endpoint_template.format(**context)
        endpoint = api_cfg.get("endpoint")
        if isinstance(endpoint, str):
            return endpoint.strip()
        return ""

    @staticmethod
    def _append_query_params(
        endpoint: str,
        query_params: dict,
        context: dict[str, str],
    ) -> str:
        encoded = {
            str(key): str(value).format(**context)
            for key, value in query_params.items()
        }
        separator = "&" if "?" in endpoint else "?"
        return endpoint + separator + urllib.parse.urlencode(encoded)

    @staticmethod
    def _format_mapping(template: dict, context: dict[str, str]) -> dict:
        formatted: dict[str, object] = {}
        for key, value in template.items():
            if isinstance(value, str):
                formatted[str(key)] = value.format(**context)
            else:
                formatted[str(key)] = value
        return formatted

    @staticmethod
    def _decision_from_response(body: str, decision_field: object) -> str:
        if isinstance(decision_field, str) and decision_field.strip():
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                lowered = {str(k).lower(): v for k, v in payload.items()}
                key = decision_field.strip().lower()
                if key in lowered:
                    return to_decision(lowered[key], default="Denied")
        return extract_decision_from_text_or_json(body, default="Denied")
