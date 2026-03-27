from __future__ import annotations

from typing import Any


APP_DISPLAY_NAMES = {
    "nomachine": "NoMachine",
    "teamviewer": "TeamViewer",
}

FIELD_LABELS = {
    "id": "ID",
    "ip": "IP",
}


def build_task_prompt(
    task_text: str,
    connections: dict[str, Any],
    connection_ref: str | None = None,
) -> str:
    context_lines = build_connection_context_lines(connections, connection_ref)
    if not context_lines:
        return task_text
    return task_text + "\n\n" + "\n".join(context_lines)


def build_connection_context_lines(
    connections: dict[str, Any],
    connection_ref: str | None = None,
) -> list[str]:
    if not connection_ref:
        return []

    app_key, details = resolve_connection_details(connections, connection_ref)
    connection_name = str(details.get("name") or connection_ref).strip()
    app_name = APP_DISPLAY_NAMES.get(app_key.lower(), app_key)

    lines = [
        "Connection details:",
        f"- Connection reference: {connection_ref}",
        f"- Remote connection app: {app_name}",
        f"- Connection name: {connection_name}",
    ]

    for key, value in details.items():
        if key == "name" or value in {"", None}:
            continue
        label = FIELD_LABELS.get(key, key.replace("_", " ").capitalize())
        lines.append(f"- {label}: {value}")

    return lines


def resolve_connection_details(
    connections: dict[str, Any],
    connection_ref: str,
) -> tuple[str, dict[str, Any]]:
    ref = str(connection_ref).strip()
    if not ref:
        raise ValueError("connection_ref must be a non-empty string.")

    for app_key, hosts in connections.items():
        if not isinstance(hosts, dict):
            continue
        details = hosts.get(ref)
        if isinstance(details, dict):
            return str(app_key), details

    raise KeyError(f"Unknown connection_ref '{ref}'.")
