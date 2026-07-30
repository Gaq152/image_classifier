"""Optional AI-assisted classification components."""

from .contracts import AI_REMOVAL_LABEL, PredictionResult, PredictionSuggestion
from .feature_extractor import (
    find_cuda_runtime_directory,
    is_cuda_execution_available,
)
from .incremental_classifier import IncrementalEmbeddingClassifier
from .model_registry import (
    AI_MODEL_PROFILES,
    DEFAULT_AI_MODEL_KEY,
    AIModelProfile,
    get_ai_model_profile,
    iter_ai_model_profiles,
)
from .project_config import (
    AI_PROJECT_STATE_KEY,
    default_ai_project_state,
    is_project_model_initialized,
    normalize_ai_project_state,
    project_model_path,
)
from .resource_manager import (
    AIResourceSpec,
    download_and_install_resource,
    format_resource_size,
    get_model_resource,
    get_runtime_resource,
    is_resource_installed,
    required_runtime_kind,
)

__all__ = [
    "AI_REMOVAL_LABEL",
    "AI_MODEL_PROFILES",
    "AI_PROJECT_STATE_KEY",
    "AIModelProfile",
    "AIResourceSpec",
    "DEFAULT_AI_MODEL_KEY",
    "IncrementalEmbeddingClassifier",
    "PredictionResult",
    "PredictionSuggestion",
    "default_ai_project_state",
    "download_and_install_resource",
    "find_cuda_runtime_directory",
    "format_resource_size",
    "get_ai_model_profile",
    "get_model_resource",
    "get_runtime_resource",
    "is_project_model_initialized",
    "is_cuda_execution_available",
    "iter_ai_model_profiles",
    "normalize_ai_project_state",
    "project_model_path",
    "required_runtime_kind",
    "is_resource_installed",
]
