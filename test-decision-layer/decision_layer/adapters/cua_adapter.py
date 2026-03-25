from __future__ import annotations

import asyncio
import json
import re
import subprocess
import urllib.error
import urllib.parse
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
                reason=result.reason or "CUA simulation",
                details={**result.details, "handoff": handoff, "mode": "simulate"},
            )
        if mode == "command":
            result = self._command(handoff, cua_cfg)
            return AdapterResult(
                decision=result.decision,
                reason=result.reason or "CUA command execution",
                details={**result.details, "handoff": handoff, "mode": "command"},
            )
        if mode in {"websocket", "ws"}:
            result = self._websocket(handoff, cua_cfg)
            return AdapterResult(
                decision=result.decision,
                reason=result.reason or "CUA websocket execution",
                details={**result.details, "handoff": handoff, "mode": "websocket"},
            )
        if mode == "http":
            result = self._http(handoff, cua_cfg)
            return AdapterResult(
                decision=result.decision,
                reason=result.reason or "CUA HTTP execution",
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

    def _websocket(self, handoff: dict[str, Any], cua_cfg: dict[str, Any]) -> AdapterResult:
        ws_server_url = str(cua_cfg.get("ws_server_url", "ws://localhost:8765")).strip()
        timeout_seconds = int(cua_cfg.get("timeout_seconds", 120))
        model_override = cua_cfg.get("model")
        task_prompt = self._build_cua_task_prompt(handoff, cua_cfg)

        try:
            decision, transcript = asyncio.run(
                self._websocket_task(
                    ws_server_url=ws_server_url,
                    task_prompt=task_prompt,
                    timeout_seconds=timeout_seconds,
                    model_override=model_override,
                )
            )
        except RuntimeError as exc:
            return AdapterResult(
                decision="Denied",
                reason=str(exc),
                details={"ws_server_url": ws_server_url, "task_prompt": task_prompt},
            )

        return AdapterResult(
            decision=decision,
            reason="CUA websocket task completed",
            details={
                "ws_server_url": ws_server_url,
                "model": model_override,
                "task_prompt": task_prompt,
                "transcript": transcript,
            },
        )

    async def _websocket_task(
        self,
        ws_server_url: str,
        task_prompt: str,
        timeout_seconds: int,
        model_override: Any,
    ) -> tuple[str, list[str]]:
        try:
            import websockets  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "CUA websocket mode requires the 'websockets' package on this machine."
            ) from exc

        transcript: list[str] = []
        final_decision: str | None = None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout_seconds, 1)

        async with websockets.connect(ws_server_url) as ws:
            # Server sends {"type":"ready"} on connect.
            ready_raw = await self._recv_with_deadline(ws, deadline)
            self._append_transcript_line(transcript, ready_raw)

            task_message: dict[str, Any] = {"type": "task", "content": task_prompt}
            if model_override:
                task_message["model"] = str(model_override)
            await ws.send(json.dumps(task_message))

            while True:
                raw = await self._recv_with_deadline(ws, deadline)
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    self._append_transcript_line(transcript, raw)
                    continue

                msg_type = str(message.get("type", "")).lower()
                if msg_type == "message":
                    text = str(message.get("text", ""))
                    self._append_transcript_line(transcript, text)
                    parsed = self._extract_agent_decision(text)
                    if parsed:
                        final_decision = parsed
                elif msg_type == "action":
                    self._append_transcript_line(transcript, f"[action] {message.get('detail')}")
                elif msg_type == "done":
                    break
                elif msg_type == "cancelled":
                    raise RuntimeError("CUA task was cancelled by server.")
                elif msg_type == "error":
                    raise RuntimeError(f"CUA server error: {message.get('message')}")
                else:
                    self._append_transcript_line(transcript, raw)

        if not final_decision:
            joined = "\n".join(transcript)
            final_decision = self._extract_agent_decision(joined)

        if not final_decision:
            raise RuntimeError(
                "CUA task finished without explicit decision. "
                "Ensure the CUA prompt returns 'FINAL_DECISION: Accepted|Denied'."
            )

        return final_decision, transcript[-30:]

    async def _recv_with_deadline(self, ws: Any, deadline: float) -> str:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise RuntimeError("CUA websocket task timed out.")
        try:
            return await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("CUA websocket task timed out.") from exc

    def _build_cua_task_prompt(self, handoff: dict[str, Any], cua_cfg: dict[str, Any]) -> str:
        claimant = handoff.get("claimant", {})
        claimant_name = claimant.get("name") or "Unknown"
        claimant_plate = claimant.get("license_plate") or ""
        decision_field = str(cua_cfg.get("decision_field", "completed"))

        context = {
            "building_id": str(handoff.get("building_id", "")),
            "requester_name": str(claimant_name),
            "license_plate": str(claimant_plate),
        }

        verification_url_template = (
            cua_cfg.get("verification_url_template")
            or cua_cfg.get("endpoint_template")
            or cua_cfg.get("endpoint")
        )
        verification_url = self._format_template(verification_url_template, context)

        steps = list(handoff.get("verification_steps", []))
        if verification_url:
            steps.append(f"Navigate to {verification_url}")
        steps.append(f"Read '{decision_field}' and determine if it is true or false")

        credentials = handoff.get("credentials", {})
        username = credentials.get("username", "")
        password = credentials.get("password", "")

        prompt_lines = [
            "You are an access verification agent for a car park gate operator.",
            "",
            "Claim details:",
            f"- Building: {handoff.get('building_id')}",
            f"- Driver Name: {claimant_name}",
            f"- Licence Plate: {claimant_plate}",
            "",
            "Connection details:",
            f"- Remote connection app: {handoff.get('remote_connection_app')}",
            f"- Remote host: {handoff.get('remote_host')}",
            f"- Username: {username}",
            f"- Password: {password}",
            f"- Remote verification app: {handoff.get('remote_verification_app')}",
            "",
            "Actions to perform:",
        ]
        for idx, step in enumerate(steps, start=1):
            prompt_lines.append(f"{idx}. {step}")

        prompt_lines.extend(
            [
                "",
                f"Decision rule: if '{decision_field}' is true -> Accepted; else -> Denied.",
                "Final response format: output exactly one line:",
                "FINAL_DECISION: Accepted",
                "or",
                "FINAL_DECISION: Denied",
                "Do not include anything after FINAL_DECISION.",
            ]
        )
        return "\n".join(prompt_lines)

    @staticmethod
    def _format_template(template: Any, context: dict[str, str]) -> str:
        if not isinstance(template, str) or not template.strip():
            return ""
        try:
            return template.format(**context)
        except KeyError:
            return template

    @staticmethod
    def _append_transcript_line(transcript: list[str], line: Any) -> None:
        text = str(line).strip()
        if text:
            transcript.append(text)

    @staticmethod
    def _extract_agent_decision(text: str) -> str | None:
        final_pattern = re.compile(r"final_decision\s*:\s*(accepted|denied)", re.IGNORECASE)
        match = final_pattern.search(text)
        if match:
            return "Accepted" if match.group(1).lower() == "accepted" else "Denied"

        simple_pattern = re.compile(r"^\s*(accepted|denied)\s*$", re.IGNORECASE | re.MULTILINE)
        simple_match = simple_pattern.search(text)
        if simple_match:
            return "Accepted" if simple_match.group(1).lower() == "accepted" else "Denied"

        boolean_pattern = re.compile(
            r"(?:completed|access[_\s-]?status)\s*[:=]\s*(true|false)",
            re.IGNORECASE,
        )
        bool_match = boolean_pattern.search(text)
        if bool_match:
            return to_decision(bool_match.group(1), default="Denied")
        return None

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
        context = {
            "building_id": handoff.get("building_id", ""),
            "requester_name": handoff.get("claimant", {}).get("name") or "",
            "license_plate": handoff.get("claimant", {}).get("license_plate") or "",
        }
        endpoint = self._resolve_endpoint(cua_cfg, context)
        if not endpoint:
            return AdapterResult(
                decision="Denied",
                reason="cua.endpoint or cua.endpoint_template is required in http mode.",
            )

        method = str(cua_cfg.get("http_method", "POST")).upper()
        headers = dict(cua_cfg.get("headers", {}))
        decision_field = cua_cfg.get("decision_field")
        timeout_seconds = int(cua_cfg.get("timeout_seconds", 40))
        query_params = cua_cfg.get("query_params", {})

        if isinstance(query_params, dict) and query_params:
            endpoint = self._append_query_params(endpoint, query_params, context)

        payload = None
        if method != "GET":
            headers.setdefault("Content-Type", "application/json")
            payload_template = cua_cfg.get("request_payload")
            payload_object = (
                self._format_mapping(payload_template, context)
                if isinstance(payload_template, dict)
                else handoff
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
                details={
                    "response": body,
                    "endpoint": endpoint,
                    "status_code": status_code,
                },
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return AdapterResult(
                decision="Denied",
                reason=f"CUA HTTP error: {exc.code}",
                details={
                    "endpoint": endpoint,
                    "status_code": int(exc.code),
                    "response": body,
                },
            )
        except urllib.error.URLError as exc:
            return AdapterResult(
                decision="Denied",
                reason=f"CUA HTTP call failed: {exc}",
                details={"endpoint": endpoint},
            )

    @staticmethod
    def _resolve_endpoint(cua_cfg: dict[str, Any], context: dict[str, str]) -> str:
        endpoint_template = cua_cfg.get("endpoint_template")
        if isinstance(endpoint_template, str) and endpoint_template.strip():
            return endpoint_template.format(**context)
        endpoint = cua_cfg.get("endpoint")
        if isinstance(endpoint, str):
            return endpoint.strip()
        return ""

    @staticmethod
    def _append_query_params(
        endpoint: str,
        query_params: dict[str, Any],
        context: dict[str, str],
    ) -> str:
        encoded = {
            str(key): str(value).format(**context)
            for key, value in query_params.items()
        }
        separator = "&" if "?" in endpoint else "?"
        return endpoint + separator + urllib.parse.urlencode(encoded)

    @staticmethod
    def _format_mapping(template: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
        formatted: dict[str, Any] = {}
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
