import pytest
from pydantic import ValidationError

from core.events import EVENT_PAYLOAD_TYPES, EventType, TokensUsedPayload

# The minimum set from the build spec's event taxonomy. This test fails if
# anyone adds or renames a member without updating the spec, or drifts from
# it by using a free string instead of the enum.
SPEC_EVENT_TYPES = {
    "run_started",
    "run_finished",
    "run_cancelled",
    "task_created",
    "task_claimed",
    "task_started",
    "task_blocked",
    "task_completed",
    "task_failed",
    "tool_call_started",
    "tool_call_finished",
    "tokens_used",
    "artifact_written",
    "verdict_issued",
    "budget_warning",
    "budget_exceeded",
    "approval_requested",
    "approval_granted",
    "approval_denied",
    "agent_heartbeat",
    "agent_error",
}


def test_event_type_matches_the_spec_taxonomy_exactly() -> None:
    assert {member.value for member in EventType} == SPEC_EVENT_TYPES


def test_every_event_type_has_a_registered_payload_model() -> None:
    assert set(EVENT_PAYLOAD_TYPES.keys()) == set(EventType)


def test_payload_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TokensUsedPayload(
            tier="coder",
            prompt=100,
            completion=50,
            latency_ms=200,
            extra="not part of the schema",  # type: ignore[call-arg]
        )


def test_tokens_used_payload_requires_all_fields() -> None:
    payload = TokensUsedPayload(tier="coder", prompt=100, completion=50, latency_ms=200)

    assert payload.tier == "coder"
