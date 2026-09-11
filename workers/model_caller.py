"""How a worker actually calls a model: always through the LiteLLM proxy,
addressed by the tier's resolved endpoint. Never a model name in sight
here — that would violate design rule 1.
"""

from __future__ import annotations

import os
import time
from typing import Protocol

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from registry.resolver import EndpointConfig


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class ModelCaller(Protocol):
    def __call__(self, endpoint: EndpointConfig, prompt: str) -> ModelResponse: ...


class LiteLLMCaller:
    """Calls a resolved endpoint through its (always OpenAI-compatible)
    LiteLLM proxy address."""

    def __call__(self, endpoint: EndpointConfig, prompt: str) -> ModelResponse:
        client = OpenAI(
            base_url=endpoint.api_base,
            api_key=os.environ.get("LITELLM_MASTER_KEY", "sk-local"),
        )

        started = time.perf_counter()
        response = client.chat.completions.create(
            model=endpoint.model,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        choice = response.choices[0].message.content or ""
        usage = response.usage
        return ModelResponse(
            text=choice,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
        )
