from pathlib import Path

from registry.generate_litellm_config import build_litellm_config

REGISTRY_PATH = Path(__file__).parent.parent.parent / "registry" / "models.yaml"


def test_every_endpoint_becomes_a_litellm_model_list_entry() -> None:
    config = build_litellm_config(REGISTRY_PATH)

    model_names = {entry["model_name"] for entry in config["model_list"]}
    assert model_names == {"qwen3.6-27b", "gemma4-12b", "claude-sonnet"}


def test_anthropic_endpoint_uses_an_env_var_reference_not_a_literal_key() -> None:
    config = build_litellm_config(REGISTRY_PATH)

    claude_entry = next(e for e in config["model_list"] if e["model_name"] == "claude-sonnet")
    assert claude_entry["litellm_params"]["api_key"] == "os.environ/ANTHROPIC_API_KEY"


def test_ollama_backed_endpoint_carries_its_api_base() -> None:
    config = build_litellm_config(REGISTRY_PATH)

    qwen_entry = next(e for e in config["model_list"] if e["model_name"] == "qwen3.6-27b")
    assert "api_base" in qwen_entry["litellm_params"]
