"""Built-in AI model profiles exposed by the desktop UI."""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class AIModelProfile:
    """One versioned base encoder option."""

    key: str
    display_name: str
    short_name: str
    description: str
    model_dir_name: str
    project_model_file: str
    expected_model_id: str
    cpu_note: str
    recommended_gpu: bool = False


AI_MODEL_PROFILES: Dict[str, AIModelProfile] = {
    "speed": AIModelProfile(
        key="speed",
        display_name="速度优先",
        short_name="速度",
        description="MobileNetV3-Large，适合低配置 CPU 和快速浏览。",
        model_dir_name="mobilenet_v3_large_embedding_v1",
        project_model_file="ai_model_speed_v1.npz",
        expected_model_id="mobilenet-v3-large-imagenet-embedding-v1",
        cpu_note="CPU 推荐：模型较小，推理速度最快。",
    ),
    "balanced": AIModelProfile(
        key="balanced",
        display_name="均衡版本",
        short_name="均衡",
        description="ResNet18 + 空间颜色特征，兼顾速度与准确率。",
        model_dir_name="resnet18_embedding_v1",
        project_model_file="ai_model_balanced_v1.npz",
        expected_model_id="resnet18-imagenet-embedding-v1",
        cpu_note="CPU 推荐：当前默认版本。",
    ),
    "accuracy": AIModelProfile(
        key="accuracy",
        display_name="精度优先",
        short_name="精度",
        description="DINOv2 ViT-S/14，少样本迁移能力更强，但推理更慢。",
        model_dir_name="dinov2_vits14_embedding_v1",
        project_model_file="ai_model_accuracy_v1.npz",
        expected_model_id="dinov2-vits14-embedding-v1",
        cpu_note="CPU 运行可能较慢；建议后续在 NVIDIA GPU 上使用。",
        recommended_gpu=True,
    ),
}

DEFAULT_AI_MODEL_KEY = "balanced"


def get_ai_model_profile(key: str) -> AIModelProfile:
    """Return a profile, falling back to the balanced version."""
    return AI_MODEL_PROFILES.get(key, AI_MODEL_PROFILES[DEFAULT_AI_MODEL_KEY])


def iter_ai_model_profiles() -> Tuple[AIModelProfile, ...]:
    """Return profiles in the product-facing order."""
    return tuple(AI_MODEL_PROFILES[key] for key in ("speed", "balanced", "accuracy"))
