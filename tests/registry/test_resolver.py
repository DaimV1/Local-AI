from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from registry.resolver import (
    Registry,
    UnknownEndpointError,
    UnknownTierError,
    load_registry,
    resolve_tier,
)

REGISTRY_PATH = Path(__file__).parent.parent.parent / "registry" / "models.yaml"


def test_the_shipped_registry_loads_and_validates() -> None:
    registry = load_registry(REGISTRY_PATH)

    assert "planner" in registry.tiers
    assert "coder" in registry.tiers


def test_resolve_tier_with_fallback_returns_both_endpoints() -> None:
    resolved = resolve_tier("planner", REGISTRY_PATH)

    assert resolved.tier == "planner"
    assert resolved.primary.provider == "openai"
    assert resolved.fallback is not None
    assert resolved.max_context == 128000


def test_resolve_tier_without_fallback_leaves_it_none() -> None:
    resolved = resolve_tier("judge", REGISTRY_PATH)

    assert resolved.fallback is None


def test_bulk_tier_carries_its_concurrency_limit() -> None:
    resolved = resolve_tier("bulk", REGISTRY_PATH)

    assert resolved.concurrency_limit == 4


def test_unknown_tier_raises_a_clear_error() -> None:
    with pytest.raises(UnknownTierError):
        resolve_tier("nonexistent-tier", REGISTRY_PATH)


def test_unknown_endpoint_reference_raises_a_clear_error(tmp_path: Path) -> None:
    bad_registry = tmp_path / "models.yaml"
    bad_registry.write_text(
        yaml.safe_dump(
            {
                "tiers": {"planner": {"primary": "local/does-not-exist"}},
                "endpoints": {},
            }
        )
    )

    with pytest.raises(UnknownEndpointError):
        resolve_tier("planner", bad_registry)


def test_registry_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    bad_registry = tmp_path / "models.yaml"
    bad_registry.write_text(yaml.safe_dump({"tiers": {}, "endpoints": {}, "typo_field": 1}))

    with pytest.raises(ValidationError):
        Registry.model_validate(yaml.safe_load(bad_registry.read_text()))
