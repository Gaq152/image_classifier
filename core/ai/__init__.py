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

__all__ = [
    "AI_REMOVAL_LABEL",
    "AI_MODEL_PROFILES",
    "AI_PROJECT_STATE_KEY",
    "AIModelProfile",
    "DEFAULT_AI_MODEL_KEY",
    "IncrementalEmbeddingClassifier",
    "PredictionResult",
    "PredictionSuggestion",
    "default_ai_project_state",
    "find_cuda_runtime_directory",
    "get_ai_model_profile",
    "is_project_model_initialized",
    "is_cuda_execution_available",
    "iter_ai_model_profiles",
    "normalize_ai_project_state",
    "project_model_path",
]
