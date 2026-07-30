"""Tests for project-level AI initialization metadata."""

from core.ai import (
    AI_PROJECT_STATE_KEY,
    default_ai_project_state,
    is_project_model_initialized,
    normalize_ai_project_state,
    project_model_path,
)


def test_project_model_requires_json_marker_and_local_file(tmp_path):
    state = default_ai_project_state()
    state["models"]["balanced"] = {
        "initialized": True,
        "project_model_file": "ai_model_balanced_v1.npz",
    }

    assert not is_project_model_initialized(state, tmp_path, "balanced")

    project_model_path(tmp_path, "balanced").touch()

    assert is_project_model_initialized(state, tmp_path, "balanced")


def test_each_profile_uses_an_independent_project_model_file(tmp_path):
    paths = {
        project_model_path(tmp_path, key).name
        for key in ("speed", "balanced", "accuracy")
    }

    assert paths == {
        "ai_model_speed_v1.npz",
        "ai_model_balanced_v1.npz",
        "ai_model_accuracy_v1.npz",
    }


def test_invalid_project_ai_state_falls_back_to_balanced():
    state = normalize_ai_project_state(
        {"active_model": "unknown", "models": [], "enabled": 1}
    )

    assert state["active_model"] == "balanced"
    assert state["models"] == {}
    assert state["enabled"] is True
    assert state["learn_removed_images"] is False
    assert AI_PROJECT_STATE_KEY == "ai_assistant"


def test_removed_image_learning_is_explicitly_opt_in():
    assert default_ai_project_state()["learn_removed_images"] is False
    assert normalize_ai_project_state(
        {"learn_removed_images": 1}
    )["learn_removed_images"] is True
