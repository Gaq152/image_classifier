"""Project-level AI configuration stored in classification_state.json."""

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from .model_registry import DEFAULT_AI_MODEL_KEY, get_ai_model_profile


AI_PROJECT_STATE_KEY = "ai_assistant"
AI_PROJECT_SCHEMA_VERSION = 1


def default_ai_project_state() -> Dict[str, Any]:
    """Create an independent default project AI state."""
    return {
        "schema_version": AI_PROJECT_SCHEMA_VERSION,
        "enabled": False,
        "active_model": DEFAULT_AI_MODEL_KEY,
        "learn_removed_images": False,
        "models": {},
    }


def normalize_ai_project_state(value: Any) -> Dict[str, Any]:
    """Normalize persisted data while keeping forward-compatible fields."""
    state = default_ai_project_state()
    if not isinstance(value, dict):
        return state
    state.update(deepcopy(value))
    if state.get("active_model") not in ("speed", "balanced", "accuracy"):
        state["active_model"] = DEFAULT_AI_MODEL_KEY
    if not isinstance(state.get("models"), dict):
        state["models"] = {}
    state["schema_version"] = AI_PROJECT_SCHEMA_VERSION
    state["enabled"] = bool(state.get("enabled", False))
    state["learn_removed_images"] = bool(
        state.get("learn_removed_images", False)
    )
    return state


def project_model_path(project_dir: Path, model_key: str) -> Path:
    """Return the project-local learned feature store path."""
    profile = get_ai_model_profile(model_key)
    return Path(project_dir) / profile.project_model_file


def is_project_model_initialized(
    state: Dict[str, Any], project_dir: Path, model_key: str
) -> bool:
    """Require both the JSON marker and its project-local model file."""
    models = state.get("models", {}) if isinstance(state, dict) else {}
    record = models.get(model_key, {}) if isinstance(models, dict) else {}
    if not isinstance(record, dict) or not record.get("initialized"):
        return False
    cache_name = record.get("project_model_file")
    expected_name = get_ai_model_profile(model_key).project_model_file
    if cache_name != expected_name:
        return False
    return (Path(project_dir) / cache_name).is_file()
