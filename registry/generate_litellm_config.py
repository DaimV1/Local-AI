"""Generate the LiteLLM proxy config from registry/models.yaml.

Run this after any change to models.yaml, before `docker compose up`:

    uv run python -m registry.generate_litellm_config
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from registry.resolver import DEFAULT_REGISTRY_PATH, load_registry

DEFAULT_OUTPUT_PATH = Path(__file__).parent.parent / "docker" / "litellm_config.generated.yaml"


def build_litellm_config(registry_path: Path | str = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    registry = load_registry(registry_path)
    model_list = []
    for endpoint in registry.endpoints.values():
        backend = endpoint.backend
        litellm_params: dict[str, object] = {"model": f"{backend.provider}/{backend.model}"}
        if backend.api_base:
            litellm_params["api_base"] = backend.api_base
        if backend.api_key_env:
            litellm_params["api_key"] = f"os.environ/{backend.api_key_env}"
        model_list.append({"model_name": endpoint.model, "litellm_params": litellm_params})
    return {"model_list": model_list}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=DEFAULT_REGISTRY_PATH, type=Path)
    parser.add_argument("--out", default=DEFAULT_OUTPUT_PATH, type=Path)
    args = parser.parse_args()

    config = build_litellm_config(args.registry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(config, sort_keys=False))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
