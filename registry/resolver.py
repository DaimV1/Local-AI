"""Tier -> endpoint resolution. The only code that reads models.yaml.

Design rule 1: agents never name a model, they declare a capability tier
and this module maps that tier to a model endpoint. Nothing here hardcodes
a model identifier — every string comes from models.yaml at load time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_REGISTRY_PATH = Path(__file__).parent / "models.yaml"


class BackendConfig(BaseModel):
    """How the LiteLLM proxy reaches the real backend for an endpoint."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    api_base: str | None = None
    api_key_env: str | None = None


class EndpointConfig(BaseModel):
    """How a worker calls a model: always through the LiteLLM proxy."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    api_base: str
    model: str
    backend: BackendConfig


class TierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str
    fallback: str | None = None
    max_context: int | None = None
    concurrency_limit: int | None = None


class ResolvedTier(BaseModel):
    """What a worker needs to call its tier's model."""

    model_config = ConfigDict(extra="forbid")

    tier: str
    primary: EndpointConfig
    fallback: EndpointConfig | None = None
    max_context: int | None = None
    concurrency_limit: int | None = None


class UnknownTierError(KeyError):
    def __init__(self, tier: str) -> None:
        super().__init__(f"unknown capability tier: {tier!r}")
        self.tier = tier


class UnknownEndpointError(KeyError):
    def __init__(self, endpoint: str) -> None:
        super().__init__(f"unknown endpoint: {endpoint!r}")
        self.endpoint = endpoint


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tiers: dict[str, TierConfig]
    endpoints: dict[str, EndpointConfig]

    def resolve(self, tier: str) -> ResolvedTier:
        try:
            tier_config = self.tiers[tier]
        except KeyError:
            raise UnknownTierError(tier) from None

        try:
            primary = self.endpoints[tier_config.primary]
        except KeyError:
            raise UnknownEndpointError(tier_config.primary) from None

        fallback = None
        if tier_config.fallback is not None:
            try:
                fallback = self.endpoints[tier_config.fallback]
            except KeyError:
                raise UnknownEndpointError(tier_config.fallback) from None

        return ResolvedTier(
            tier=tier,
            primary=primary,
            fallback=fallback,
            max_context=tier_config.max_context,
            concurrency_limit=tier_config.concurrency_limit,
        )


def load_registry(path: Path | str = DEFAULT_REGISTRY_PATH) -> Registry:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
    return Registry.model_validate(data)


def resolve_tier(tier: str, path: Path | str = DEFAULT_REGISTRY_PATH) -> ResolvedTier:
    return load_registry(path).resolve(tier)
