"""Stable input/output contracts for AI classification engines."""

from dataclasses import dataclass
from typing import Optional, Tuple


AI_REMOVAL_LABEL = "__ai_removal__"


@dataclass(frozen=True)
class PredictionSuggestion:
    """One category candidate returned by an engine."""

    category: str
    similarity: float


@dataclass(frozen=True)
class PredictionResult:
    """Model-independent prediction result consumed by the desktop UI."""

    request_id: int
    image_path: str
    suggestions: Tuple[PredictionSuggestion, ...]
    uncertain: bool
    provider: str
    latency_ms: float
    reason: Optional[str] = None
