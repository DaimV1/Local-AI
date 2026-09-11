"""Design rule 1: agents never name a model.

This test derives every literal model identifier from models.yaml itself
(never hardcodes one) and fails if any of those strings appear in code
outside /registry — the only place a model name is allowed to exist.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "registry" / "models.yaml"

# Directories that could plausibly hardcode a model name in violation of
# design rule 1. /registry is the source of truth, and /tests legitimately
# asserts on registry-derived values (e.g. the generated LiteLLM config),
# so neither is scanned.
SCAN_DIRS = ["core", "orchestrator", "workers", "api"]
SCAN_SUFFIXES = {".py"}

# Below this length a "model name" (e.g. a bare version number) is too
# likely to collide with unrelated code and would make the test noisy.
MIN_INTERESTING_LENGTH = 4


def _collect_model_strings(registry_path: Path) -> set[str]:
    data = yaml.safe_load(registry_path.read_text())
    names: set[str] = set()
    for endpoint_key, endpoint in data.get("endpoints", {}).items():
        names.add(endpoint_key.rsplit("/", 1)[-1])
        if model := endpoint.get("model"):
            names.add(model)
        if backend_model := endpoint.get("backend", {}).get("model"):
            names.add(backend_model)
    return {name for name in names if len(name) >= MIN_INTERESTING_LENGTH}


def test_model_names_do_not_leak_outside_registry() -> None:
    model_strings = _collect_model_strings(REGISTRY_PATH)
    assert model_strings, "sanity check: expected to find model identifiers in models.yaml"

    offenders = []
    for dirname in SCAN_DIRS:
        directory = REPO_ROOT / dirname
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                continue
            text = path.read_text()
            for name in model_strings:
                if name in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {name!r}")

    assert not offenders, "Model name(s) leaked outside /registry:\n" + "\n".join(offenders)
