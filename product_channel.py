"""Product identity and isolated update-channel metadata."""

from __future__ import annotations

from typing import Dict, Optional

import _build_channel_


STANDARD_EDITION = "standard"
AI_EDITION = "ai"
SUPPORTED_EDITIONS = (STANDARD_EDITION, AI_EDITION)

_PRODUCTS = {
    STANDARD_EDITION: {
        "edition": STANDARD_EDITION,
        "channel": "stable",
        "application_name": "图像分类工具",
        "ascii_executable_base": "ImageClassifier",
        "chinese_executable_base": "图像分类工具",
        "release_tag_prefix": "v",
        "rolling_release_tag": None,
        "update_subdirectory": "update",
    },
    AI_EDITION: {
        "edition": AI_EDITION,
        "channel": "ai",
        "application_name": "图像分类工具 AI版",
        "ascii_executable_base": "ImageClassifierAI",
        "chinese_executable_base": "图像分类工具AI版",
        "release_tag_prefix": "ai-v",
        "rolling_release_tag": "ai-latest",
        "update_subdirectory": "update/ai",
    },
}


def normalize_edition(edition: Optional[str]) -> str:
    """Normalize unknown build values to the public standard edition."""
    value = str(edition or "").strip().lower()
    return value if value in SUPPORTED_EDITIONS else STANDARD_EDITION


def get_current_edition() -> str:
    """Return the edition embedded at build time."""
    return normalize_edition(getattr(_build_channel_, "APP_EDITION", None))


def get_product_info(edition: Optional[str] = None) -> Dict[str, object]:
    """Return a copy of product metadata for one edition."""
    key = get_current_edition() if edition is None else normalize_edition(edition)
    return dict(_PRODUCTS[key])


def validate_manifest_edition(
    manifest: Dict[str, object], edition: Optional[str] = None
) -> None:
    """Reject cross-channel manifests before an executable can download them.

    Old standard manifests did not contain edition/channel fields, so the
    standard build keeps accepting that legacy shape. AI builds require an
    explicit AI marker and can therefore never consume the public channel.
    """
    expected = get_product_info(edition)
    manifest_edition = str(manifest.get("edition", "")).strip().lower()
    manifest_channel = str(manifest.get("channel", "")).strip().lower()

    if expected["edition"] == STANDARD_EDITION:
        if manifest_edition not in ("", STANDARD_EDITION):
            raise ValueError("更新清单属于其他产品版本")
        if manifest_channel not in ("", "stable"):
            raise ValueError("更新清单属于其他更新通道")
        return

    if manifest_edition != expected["edition"]:
        raise ValueError("AI 版拒绝使用非 AI 更新清单")
    if manifest_channel != expected["channel"]:
        raise ValueError("AI 版更新通道不匹配")
