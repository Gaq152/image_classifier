"""Evaluate the incremental embedding classifier on an existing project state."""

# ruff: noqa: E402 -- direct script execution needs the repository root first.

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    f1_score,
)
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, train_test_split
from torchvision.models import ResNet18_Weights, resnet18

from core.ai.feature_extractor import (
    letterbox_rgb,
    read_rgb_image,
    spatial_color_features,
)


INPUT_SIZE = 224
BATCH_SIZE = 64
FEATURE_CACHE_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen ResNet18 embeddings with balanced KNN."
    )
    parser.add_argument("state", type=Path, help="classification_state.json path")
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path.home()
        / "image_classifier"
        / "ai_cache"
        / "embedding_evaluation_v1.npz",
        help="Local feature cache path",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--frame-block-size", type=int, default=10)
    parser.add_argument(
        "--include-removed",
        action="store_true",
        help="Treat removed_images as a fourth 'remove' category",
    )
    return parser.parse_args()


def extract_features(
    paths: np.ndarray, batch_size: int
) -> tuple[np.ndarray, np.ndarray]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = torch.nn.Identity()
    model.eval().to(device)

    mean = torch.tensor([0.485, 0.456, 0.406], device=device).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device=device).view(1, 3, 1, 1)
    deep_batches = []
    color_features = []
    started_at = time.perf_counter()

    with torch.inference_mode():
        for start in range(0, len(paths), batch_size):
            rgb_images = [
                read_rgb_image(path) for path in paths[start : start + batch_size]
            ]
            batch = np.stack(
                [
                    letterbox_rgb(rgb, INPUT_SIZE, INPUT_SIZE, (124, 116, 104))
                    for rgb in rgb_images
                ]
            )
            tensor = (
                torch.from_numpy(batch)
                .permute(0, 3, 1, 2)
                .to(device=device, dtype=torch.float32)
                / 255.0
            )
            tensor = (tensor - mean) / std
            embeddings = model(tensor).cpu().numpy().astype(np.float32)
            embeddings /= np.maximum(
                np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8
            )
            deep_batches.append(embeddings)
            color_features.extend(spatial_color_features(rgb) for rgb in rgb_images)

            completed = min(start + batch_size, len(paths))
            elapsed = time.perf_counter() - started_at
            print(f"提取特征 {completed}/{len(paths)}，耗时 {elapsed:.1f}s", flush=True)

    return np.concatenate(deep_batches), np.stack(color_features)


def combine_features(
    deep_train: np.ndarray,
    color_train: np.ndarray,
    deep_test: np.ndarray,
    color_test: np.ndarray,
    color_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    if color_weight == 0:
        return deep_train, deep_test

    mean = color_train.mean(0, keepdims=True)
    std = color_train.std(0, keepdims=True)
    normalized_train = (color_train - mean) / np.maximum(std, 1e-3)
    normalized_test = (color_test - mean) / np.maximum(std, 1e-3)
    normalized_train /= np.maximum(
        np.linalg.norm(normalized_train, axis=1, keepdims=True), 1e-8
    )
    normalized_test /= np.maximum(
        np.linalg.norm(normalized_test, axis=1, keepdims=True), 1e-8
    )

    train = np.concatenate([deep_train, normalized_train * color_weight], axis=1)
    test = np.concatenate([deep_test, normalized_test * color_weight], axis=1)
    train /= np.maximum(np.linalg.norm(train, axis=1, keepdims=True), 1e-8)
    test /= np.maximum(np.linalg.norm(test, axis=1, keepdims=True), 1e-8)
    return train, test


def predict_balanced_knn(
    train_features: np.ndarray,
    train_labels: np.ndarray,
    test_features: np.ndarray,
    labels: list[str],
    neighbors: int,
) -> np.ndarray:
    """Average each class' best neighbors so large classes cannot dominate."""
    similarity = test_features @ train_features.T
    scores = np.empty((len(test_features), len(labels)), dtype=np.float32)
    for class_index, label in enumerate(labels):
        class_similarity = similarity[:, train_labels == label]
        take = min(neighbors, class_similarity.shape[1])
        best = np.partition(class_similarity, -take, axis=1)[:, -take:]
        scores[:, class_index] = best.mean(axis=1)
    return np.asarray(labels)[scores.argmax(1)]


def load_samples(
    state_path: Path, include_removed: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    items = [
        (path, str(label))
        for path, label in state.get("classified_images", {}).items()
        if isinstance(label, str)
    ]
    if include_removed:
        items.extend(
            (path, "remove") for path in state.get("removed_images", [])
        )
    paths = np.asarray([path for path, _ in items])
    labels = np.asarray([label for _, label in items])
    frames = []
    for index, path in enumerate(paths):
        match = re.search(r"_frame_(\d+)", Path(path).name)
        frames.append(int(match.group(1)) if match else index)
    return paths, labels, np.asarray(frames)


def get_clip_ids(paths: np.ndarray) -> np.ndarray:
    return np.asarray(
        [re.sub(r"_frame_.*$", "", Path(path).name) for path in paths]
    )


def get_temporal_groups(
    paths: np.ndarray, frames: np.ndarray, frame_block_size: int
) -> np.ndarray:
    clip_ids = get_clip_ids(paths)
    return np.asarray(
        [
            f"{clip_id}:{frame // frame_block_size}"
            for clip_id, frame in zip(clip_ids, frames)
        ]
    )


def load_or_extract(
    paths: np.ndarray,
    labels: np.ndarray,
    frames: np.ndarray,
    cache_path: Path,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    if cache_path.exists():
        cached = np.load(cache_path, allow_pickle=False)
        if int(cached["version"][0]) == FEATURE_CACHE_VERSION and np.array_equal(
            cached["paths"], paths
        ):
            print(f"读取特征缓存: {cache_path}")
            return cached["deep"], cached["colors"]

    deep, colors = extract_features(paths, batch_size)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path,
        version=np.asarray([FEATURE_CACHE_VERSION]),
        paths=paths,
        labels=labels,
        frames=frames,
        deep=deep,
        colors=colors,
    )
    print(f"已保存特征缓存: {cache_path}")
    return deep, colors


def evaluate(
    deep: np.ndarray,
    colors: np.ndarray,
    labels: np.ndarray,
    paths: np.ndarray,
    frames: np.ndarray,
    frame_block_size: int,
) -> None:
    class_names = sorted(set(labels))
    groups = get_temporal_groups(paths, frames, frame_block_size)
    configurations = [
        (weight, neighbors)
        for weight in (0.0, 0.15, 0.3, 0.6, 1.0)
        for neighbors in (1, 3, 5, 10)
    ]
    results = {configuration: [] for configuration in configurations}

    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    for fold, (train_indices, test_indices) in enumerate(
        splitter.split(deep, labels, groups), start=1
    ):
        print(
            f"分组折 {fold}: 训练 {dict(Counter(labels[train_indices]))}, "
            f"测试 {dict(Counter(labels[test_indices]))}"
        )
        if len(set(labels[train_indices])) < len(class_names) or len(
            set(labels[test_indices])
        ) < len(class_names):
            print("  跳过：该折没有覆盖全部类别")
            continue

        for color_weight, neighbors in configurations:
            train_features, test_features = combine_features(
                deep[train_indices],
                colors[train_indices],
                deep[test_indices],
                colors[test_indices],
                color_weight,
            )
            predictions = predict_balanced_knn(
                train_features,
                labels[train_indices],
                test_features,
                class_names,
                neighbors,
            )
            results[(color_weight, neighbors)].append(
                (
                    f1_score(labels[test_indices], predictions, average="macro"),
                    balanced_accuracy_score(labels[test_indices], predictions),
                    accuracy_score(labels[test_indices], predictions),
                )
            )

    ranked_results = []
    for configuration, values in results.items():
        if not values:
            continue
        scores = np.asarray(values)
        ranked_results.append(
            (
                scores[:, 0].mean(),
                scores[:, 1].mean(),
                scores[:, 2].mean(),
                configuration,
                len(values),
            )
        )

    print("\n按连续帧分组的交叉验证（前 12 名）")
    for macro_f1, balanced_accuracy, accuracy, configuration, fold_count in sorted(
        ranked_results, reverse=True
    )[:12]:
        print(
            f"颜色权重={configuration[0]:.2f}, K={configuration[1]:2d}, "
            f"有效折={fold_count}: macro-F1={macro_f1:.3f}, "
            f"balanced-acc={balanced_accuracy:.3f}, accuracy={accuracy:.3f}"
        )

    best_configuration = max(ranked_results)[3]

    clip_ids = get_clip_ids(paths)
    clip_count = len(set(clip_ids))
    if clip_count >= 2:
        held_out_labels = []
        held_out_predictions = []
        clip_splitter = GroupKFold(n_splits=clip_count)
        for train_indices, test_indices in clip_splitter.split(deep, labels, clip_ids):
            if len(set(labels[train_indices])) < len(class_names):
                continue
            train_features, test_features = combine_features(
                deep[train_indices],
                colors[train_indices],
                deep[test_indices],
                colors[test_indices],
                best_configuration[0],
            )
            predictions = predict_balanced_knn(
                train_features,
                labels[train_indices],
                test_features,
                class_names,
                best_configuration[1],
            )
            held_out_labels.extend(labels[test_indices])
            held_out_predictions.extend(predictions)
        if held_out_labels:
            print(
                f"\n逐视频留出，采用分块验证最优参数: {best_configuration}"
            )
            print(
                classification_report(
                    held_out_labels,
                    held_out_predictions,
                    labels=class_names,
                    digits=3,
                    zero_division=0,
                )
            )

    indices = np.arange(len(labels))
    train_indices, test_indices = train_test_split(
        indices, test_size=0.2, random_state=42, stratify=labels
    )
    train_features, test_features = combine_features(
        deep[train_indices],
        colors[train_indices],
        deep[test_indices],
        colors[test_indices],
        best_configuration[0],
    )
    predictions = predict_balanced_knn(
        train_features,
        labels[train_indices],
        test_features,
        class_names,
        best_configuration[1],
    )
    print(f"\n随机留出集，采用分组验证最优参数: {best_configuration}")
    print(classification_report(labels[test_indices], predictions, digits=3))


def main() -> None:
    args = parse_args()
    paths, labels, frames = load_samples(args.state, args.include_removed)
    print(
        f"样本数={len(labels)}, 类别={dict(Counter(labels))}, "
        f"视频数={len(set(get_clip_ids(paths)))}, "
        f"时序分组数={len(set(get_temporal_groups(paths, frames, args.frame_block_size)))}"
    )
    deep, colors = load_or_extract(paths, labels, frames, args.cache, args.batch_size)
    evaluate(deep, colors, labels, paths, frames, args.frame_block_size)


if __name__ == "__main__":
    main()
