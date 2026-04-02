from __future__ import annotations

import copy
import datetime as dt
import json
import uuid
from typing import Any

PROVENANCE_KEY = "provenance"
PROVENANCE_STANDARD = "W3C PROV-O"
PROVENANCE_PROFILE = "labelme/provenance/v1"


def utc_now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def new_session_id() -> str:
    return uuid.uuid4().hex


def new_annotation_id() -> str:
    return uuid.uuid4().hex


def normalize_agent(agent: dict[str, Any] | None) -> dict[str, Any]:
    if agent is None:
        return {"label": "unknown", "type": "Agent", "properties": {}}
    normalized = {
        "label": str(agent.get("label", "unknown")),
        "type": str(agent.get("type", "Agent")),
        "properties": copy.deepcopy(agent.get("properties", {})),
    }
    if "id" in agent and agent["id"] is not None:
        normalized["id"] = str(agent["id"])
    return normalized


def agent_signature(agent: dict[str, Any]) -> str:
    return json.dumps(normalize_agent(agent), sort_keys=True, separators=(",", ":"))


def default_interactive_agent() -> dict[str, Any]:
    return {
        "label": "interactive-user",
        "type": "Person",
        "properties": {},
    }


def model_agent(model_name: str, *, provider: str = "osam") -> dict[str, Any]:
    return {
        "label": model_name,
        "type": "SoftwareAgent",
        "properties": {
            "provider": provider,
            "model_name": model_name,
        },
    }


def ensure_provenance(shape) -> dict[str, Any]:
    provenance = shape.other_data.get(PROVENANCE_KEY)
    if provenance is None:
        provenance = {
            "standard": PROVENANCE_STANDARD,
            "profile": PROVENANCE_PROFILE,
            "annotation_id": new_annotation_id(),
            "events": [],
        }
        shape.other_data[PROVENANCE_KEY] = provenance
    provenance.setdefault("standard", PROVENANCE_STANDARD)
    provenance.setdefault("profile", PROVENANCE_PROFILE)
    provenance.setdefault("annotation_id", new_annotation_id())
    provenance.setdefault("events", [])
    return provenance


def get_annotation_id(shape) -> str:
    return ensure_provenance(shape)["annotation_id"]


def reassign_annotation_id(shape) -> str:
    provenance = ensure_provenance(shape)
    provenance["annotation_id"] = new_annotation_id()
    return provenance["annotation_id"]


def _merge_event_properties(old: dict[str, Any], new: dict[str, Any]) -> None:
    old_kinds = list(old.get("kinds", []))
    new_kinds = list(new.get("kinds", []))
    old["kinds"] = sorted(set(old_kinds) | set(new_kinds))
    for key, value in new.items():
        if key == "kinds":
            continue
        if key not in old:
            old[key] = copy.deepcopy(value)


def _can_collapse(last_event: dict[str, Any], new_event: dict[str, Any]) -> bool:
    last_session = last_event.get("properties", {}).get("session_id")
    new_session = new_event.get("properties", {}).get("session_id")
    if last_session != new_session:
        return False
    return agent_signature(last_event["agent"]) == agent_signature(new_event["agent"])


def _collapse_or_append(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    if not events:
        events.append(event)
        return

    last = events[-1]
    if not _can_collapse(last, event):
        events.append(event)
        return

    # Do not collapse derive events - they represent a new branch in the lineage
    if event["action"] == "derive":
        events.append(event)
        return

    if last["action"] in {"create", "derive"} and event["action"] == "edit":
        last["ended_at"] = event["ended_at"]
        _merge_event_properties(last.setdefault("properties", {}), event.get("properties", {}))
        return

    if last["action"] == "edit" and event["action"] == "edit":
        last["ended_at"] = event["ended_at"]
        _merge_event_properties(last.setdefault("properties", {}), event.get("properties", {}))
        return

    events.append(event)


def record_event(
    shape,
    *,
    action: str,
    agent: dict[str, Any],
    session_id: str,
    properties: dict[str, Any] | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    provenance = ensure_provenance(shape)
    now = utc_now_iso()
    event = {
        "action": action,
        "agent": normalize_agent(agent),
        "started_at": started_at or now,
        "ended_at": ended_at or now,
        "properties": copy.deepcopy(properties or {}),
    }
    event["properties"].setdefault("session_id", session_id)
    event["properties"].setdefault("kinds", [])
    _collapse_or_append(provenance["events"], event)
    return provenance


def clone_shape_for_derivation(
    source_shape,
    *,
    agent: dict[str, Any],
    session_id: str,
    properties: dict[str, Any] | None = None,
):
    new_shape = source_shape.copy()
    source_annotation_id = get_annotation_id(source_shape)
    ensure_provenance(new_shape)
    reassign_annotation_id(new_shape)
    record_event(
        new_shape,
        action="derive",
        agent=agent,
        session_id=session_id,
        properties={
            "kinds": ["duplicate"],
            "source_annotation_id": source_annotation_id,
            **(properties or {}),
        },
    )
    return new_shape
