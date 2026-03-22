"""Unit tests for the provenance module."""

from __future__ import annotations

from labelme.provenance import _can_collapse
from labelme.provenance import _collapse_or_append
from labelme.provenance import agent_signature
from labelme.provenance import clone_shape_for_derivation
from labelme.provenance import default_interactive_agent
from labelme.provenance import ensure_provenance
from labelme.provenance import get_annotation_id
from labelme.provenance import model_agent
from labelme.provenance import new_annotation_id
from labelme.provenance import normalize_agent
from labelme.provenance import record_event
from labelme.provenance import reassign_annotation_id
from labelme.shape import Shape


def test_create_absorbs_same_agent_same_session_edit():
    """Test that create + edit from same agent/session collapses into one create."""
    shape = Shape(label="test")
    agent = default_interactive_agent()
    session_id = "test-session-123"

    record_event(
        shape,
        action="create",
        agent=agent,
        session_id=session_id,
        properties={"kinds": ["manual_draw", "polygon"]},
    )
    record_event(
        shape,
        action="edit",
        agent=agent,
        session_id=session_id,
        properties={"kinds": ["label_edit"]},
    )

    provenance = ensure_provenance(shape)
    assert len(provenance["events"]) == 1
    assert provenance["events"][0]["action"] == "create"
    kinds = provenance["events"][0]["properties"]["kinds"]
    assert "manual_draw" in kinds
    assert "label_edit" in kinds


def test_create_does_not_absorb_different_agent_edit():
    """Test that create by SoftwareAgent + edit by Person creates two events."""
    shape = Shape(label="test")
    create_agent = model_agent("sam2:latest")
    edit_agent = default_interactive_agent()
    session_id = "test-session-123"

    record_event(
        shape,
        action="create",
        agent=create_agent,
        session_id=session_id,
        properties={"kinds": ["ai_generate", "ai_polygon"]},
    )
    record_event(
        shape,
        action="edit",
        agent=edit_agent,
        session_id=session_id,
        properties={"kinds": ["label_edit"]},
    )

    provenance = ensure_provenance(shape)
    assert len(provenance["events"]) == 2
    assert provenance["events"][0]["action"] == "create"
    assert provenance["events"][1]["action"] == "edit"


def test_same_agent_same_session_edits_collapse():
    """Test that two edit events from same agent/session collapse into one."""
    shape = Shape(label="test")
    agent = default_interactive_agent()
    session_id = "test-session-123"

    record_event(
        shape,
        action="edit",
        agent=agent,
        session_id=session_id,
        properties={"kinds": ["geometry"]},
    )
    record_event(
        shape,
        action="edit",
        agent=agent,
        session_id=session_id,
        properties={"kinds": ["label_edit"]},
    )

    provenance = ensure_provenance(shape)
    assert len(provenance["events"]) == 1
    assert provenance["events"][0]["action"] == "edit"
    kinds = provenance["events"][0]["properties"]["kinds"]
    assert "geometry" in kinds
    assert "label_edit" in kinds


def test_different_session_edits_do_not_collapse():
    """Test that edits from different sessions do not collapse."""
    shape = Shape(label="test")
    agent = default_interactive_agent()

    record_event(
        shape,
        action="edit",
        agent=agent,
        session_id="session-1",
        properties={"kinds": ["geometry"]},
    )
    record_event(
        shape,
        action="edit",
        agent=agent,
        session_id="session-2",
        properties={"kinds": ["label_edit"]},
    )

    provenance = ensure_provenance(shape)
    assert len(provenance["events"]) == 2


def test_clone_shape_for_derivation_reassigns_annotation_id():
    """Test that clone_shape_for_derivation creates a new annotation_id and derive event."""
    source_shape = Shape(label="test")
    agent = default_interactive_agent()
    session_id = "test-session-123"

    # Create the source shape with provenance
    record_event(
        source_shape,
        action="create",
        agent=agent,
        session_id=session_id,
        properties={"kinds": ["manual_draw"]},
    )
    source_annotation_id = get_annotation_id(source_shape)

    # Clone the shape
    new_shape = clone_shape_for_derivation(
        source_shape,
        agent=agent,
        session_id=session_id,
        properties={"kinds": ["duplicate"]},
    )

    # Check that the new shape has a different annotation_id
    new_annotation_id = get_annotation_id(new_shape)
    assert new_annotation_id != source_annotation_id

    # Check that the new shape has the source history plus a derive event
    provenance = ensure_provenance(new_shape)
    assert len(provenance["events"]) == 2
    assert provenance["events"][0]["action"] == "create"
    assert provenance["events"][1]["action"] == "derive"
    assert provenance["events"][1]["properties"]["source_annotation_id"] == source_annotation_id


def test_provenance_round_trip_through_label_file_loader():
    """Test that provenance is preserved through _load_shape_json_obj."""
    from labelme._label_file import _load_shape_json_obj

    # Build a shape dict with provenance as a top-level key (on-disk format)
    shape_dict: dict = {
        "label": "test",
        "points": [[0.0, 0.0], [10.0, 10.0]],
        "shape_type": "rectangle",
        "flags": {},
        "group_id": None,
        "description": None,
        "provenance": {
            "standard": "W3C PROV-O",
            "profile": "labelme/provenance/v1",
            "annotation_id": "test-annotation-id",
            "events": [
                {
                    "action": "create",
                    "agent": {
                        "label": "test-agent",
                        "type": "Person",
                        "properties": {},
                    },
                    "started_at": "2026-03-20T15:30:00Z",
                    "ended_at": "2026-03-20T15:31:10Z",
                    "properties": {
                        "session_id": "test-session",
                        "kinds": ["manual_draw"],
                    },
                }
            ],
        },
    }

    loaded = _load_shape_json_obj(shape_dict)
    # provenance is loaded into other_data
    assert "provenance" in loaded["other_data"]
    assert loaded["other_data"]["provenance"]["annotation_id"] == "test-annotation-id"
    assert len(loaded["other_data"]["provenance"]["events"]) == 1


def test_normalize_agent():
    """Test normalize_agent function."""
    # Test with None
    assert normalize_agent(None) == {"label": "unknown", "type": "Agent", "properties": {}}

    # Test with empty dict
    assert normalize_agent({}) == {"label": "unknown", "type": "Agent", "properties": {}}

    # Test with full agent
    agent = {
        "label": "test-agent",
        "type": "Person",
        "properties": {"key": "value"},
    }
    assert normalize_agent(agent) == agent


def test_agent_signature():
    """Test agent_signature function produces consistent signatures."""
    agent1 = {
        "label": "test-agent",
        "type": "Person",
        "properties": {"key": "value"},
    }
    agent2 = {
        "label": "test-agent",
        "type": "Person",
        "properties": {"key": "value"},
    }
    agent3 = {
        "label": "different-agent",
        "type": "Person",
        "properties": {"key": "value"},
    }

    assert agent_signature(agent1) == agent_signature(agent2)
    assert agent_signature(agent1) != agent_signature(agent3)


def test_can_collapse_create_and_edit_same_agent_session():
    """Test _can_collapse with same session and agent."""
    last_event = {
        "action": "create",
        "agent": default_interactive_agent(),
        "properties": {"session_id": "session-1", "kinds": ["manual_draw"]},
    }
    new_event = {
        "action": "edit",
        "agent": default_interactive_agent(),
        "properties": {"session_id": "session-1", "kinds": ["label_edit"]},
    }
    assert _can_collapse(last_event, new_event) is True


def test_can_collapse_different_session_fails():
    """Test _can_collapse with different sessions."""
    last_event = {
        "action": "create",
        "agent": default_interactive_agent(),
        "properties": {"session_id": "session-1", "kinds": ["manual_draw"]},
    }
    new_event = {
        "action": "edit",
        "agent": default_interactive_agent(),
        "properties": {"session_id": "session-2", "kinds": ["label_edit"]},
    }
    assert _can_collapse(last_event, new_event) is False


def test_can_collapse_different_agent_fails():
    """Test _can_collapse with different agents."""
    last_event = {
        "action": "create",
        "agent": model_agent("sam2:latest"),
        "properties": {"session_id": "session-1", "kinds": ["ai_generate"]},
    }
    new_event = {
        "action": "edit",
        "agent": default_interactive_agent(),
        "properties": {"session_id": "session-1", "kinds": ["label_edit"]},
    }
    assert _can_collapse(last_event, new_event) is False


def test_collapse_or_append_with_empty_events():
    """Test _collapse_or_append with empty events list."""
    events = []
    event = {
        "action": "create",
        "agent": default_interactive_agent(),
        "properties": {"session_id": "session-1", "kinds": ["manual_draw"]},
    }
    _collapse_or_append(events, event)
    assert len(events) == 1
    assert events[0]["action"] == "create"


def test_collapse_or_append_collapses_create_and_edit():
    """Test _collapse_or_append with collapsible events."""
    events = [
        {
            "action": "create",
            "agent": default_interactive_agent(),
            "started_at": "2026-03-20T15:30:00Z",
            "ended_at": "2026-03-20T15:30:05Z",
            "properties": {"session_id": "session-1", "kinds": ["manual_draw"]},
        }
    ]
    new_event = {
        "action": "edit",
        "agent": default_interactive_agent(),
        "started_at": "2026-03-20T15:31:00Z",
        "ended_at": "2026-03-20T15:31:05Z",
        "properties": {"session_id": "session-1", "kinds": ["label_edit"]},
    }
    _collapse_or_append(events, new_event)
    assert len(events) == 1
    assert events[0]["action"] == "create"
    assert "label_edit" in events[0]["properties"]["kinds"]


def test_collapse_or_append_does_not_collapse_different_agent():
    """Test _collapse_or_append with non-collapsible events."""
    events = [
        {
            "action": "create",
            "agent": model_agent("sam2:latest"),
            "properties": {"session_id": "session-1", "kinds": ["ai_generate"]},
        }
    ]
    new_event = {
        "action": "edit",
        "agent": default_interactive_agent(),
        "properties": {"session_id": "session-1", "kinds": ["label_edit"]},
    }
    _collapse_or_append(events, new_event)
    assert len(events) == 2
    assert events[1]["action"] == "edit"


def test_model_agent_returns_software_agent():
    """Test model_agent function."""
    agent = model_agent("sam2:latest", provider="osam")
    assert agent["label"] == "sam2:latest"
    assert agent["type"] == "SoftwareAgent"
    assert agent["properties"]["provider"] == "osam"
    assert agent["properties"]["model_name"] == "sam2:latest"


def test_ensure_provenance_creates_new_when_missing():
    """Test that ensure_provenance creates new provenance if missing."""
    shape = Shape(label="test")
    assert "provenance" not in shape.other_data

    provenance = ensure_provenance(shape)

    assert "provenance" in shape.other_data
    assert provenance["standard"] == "W3C PROV-O"
    assert provenance["profile"] == "labelme/provenance/v1"
    assert "annotation_id" in provenance
    assert provenance["events"] == []


def test_ensure_provenance_returns_existing_when_present():
    """Test that ensure_provenance returns existing provenance."""
    shape = Shape(label="test")
    original_id = new_annotation_id()
    shape.other_data["provenance"] = {
        "standard": "W3C PROV-O",
        "profile": "labelme/provenance/v1",
        "annotation_id": original_id,
        "events": [],
    }

    provenance = ensure_provenance(shape)

    assert provenance["annotation_id"] == original_id


def test_reassign_annotation_id_generates_new_id():
    """Test that reassign_annotation_id generates a new ID."""
    shape = Shape(label="test")
    original_id = get_annotation_id(shape)

    new_id = reassign_annotation_id(shape)

    assert new_id != original_id
    assert shape.other_data["provenance"]["annotation_id"] == new_id
