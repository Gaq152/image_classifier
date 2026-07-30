"""Concurrency guarantees for AI prediction and incremental feedback."""

import threading
import time
from types import SimpleNamespace

import numpy as np

from core.ai import project_model_path
import ui.managers.ai_classification_manager as manager_module
from ui.managers.ai_classification_manager import AIClassificationManager


class FakeConcurrentClassifier:
    model_id = "fake-model"
    provider_label = "CPU"
    sample_count = 0
    class_counts = {}

    def __init__(self, block_learning: bool = False):
        self.block_learning = block_learning
        self.learning_started = threading.Event()
        self.release_learning = threading.Event()
        self.prediction_finished = threading.Event()
        self.learn_calls = []
        self.forget_calls = []
        self.save_calls = 0

    def learn(self, image_path, label, actual_path=None):
        self.learning_started.set()
        if self.block_learning:
            self.release_learning.wait(timeout=2)
        self.learn_calls.append((image_path, label, actual_path))
        return True

    def forget(self, image_path):
        self.forget_calls.append(image_path)
        return True

    def predict(self, request_id, image_path, rgb, categories):
        self.prediction_finished.set()
        return SimpleNamespace(request_id=request_id, image_path=image_path)

    def save(self):
        self.save_calls += 1


def _ready_manager(tmp_path, classifier):
    manager = AIClassificationManager(preferred_provider="cpu")
    manager._classifier = classifier
    manager._active_project_dir = tmp_path
    manager._active_model_key = "balanced"
    return manager


def _wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_prediction_executor_is_not_queued_behind_learning(tmp_path):
    classifier = FakeConcurrentClassifier(block_learning=True)
    manager = _ready_manager(tmp_path, classifier)
    try:
        manager.learn("image-a", "类别A", actual_path="a.jpg")
        assert classifier.learning_started.wait(timeout=1)

        manager.submit_prediction(
            "query",
            np.zeros((2, 2, 3), dtype=np.uint8),
            ("类别A", "类别B"),
        )

        assert classifier.prediction_finished.wait(timeout=1)
    finally:
        classifier.release_learning.set()
        _wait_until(lambda: not manager._feedback_running)
        manager.shutdown()


def test_feedback_for_same_image_is_coalesced_to_final_state(tmp_path):
    classifier = FakeConcurrentClassifier()
    manager = _ready_manager(tmp_path, classifier)
    try:
        manager._prediction_running = True
        manager.learn("same-image", "类别A", actual_path="a.jpg")
        manager.learn("same-image", "类别B", actual_path="b.jpg")

        assert len(manager._pending_feedback) == 1
        manager._prediction_running = False
        manager._schedule_feedback_if_ready()

        assert _wait_until(lambda: len(classifier.learn_calls) == 1)
        assert classifier.learn_calls == [
            ("same-image", "类别B", "b.jpg")
        ]
    finally:
        manager.shutdown()


def test_feedback_during_initialization_is_replayed_when_ready(tmp_path):
    classifier = FakeConcurrentClassifier()
    manager = AIClassificationManager(preferred_provider="cpu")
    manager._active_project_dir = tmp_path
    try:
        manager.learn("new-image", "类别A", actual_path="new.jpg")
        assert "new-image" in manager._pending_feedback

        manager._classifier = classifier
        manager._schedule_feedback_if_ready()

        assert _wait_until(lambda: len(classifier.learn_calls) == 1)
        assert classifier.learn_calls[0][0] == "new-image"
    finally:
        manager.shutdown()


def test_safe_reinitialize_keeps_old_model_until_atomic_swap(
    monkeypatch, tmp_path
):
    build_started = threading.Event()
    release_build = threading.Event()

    class RebuiltClassifier:
        model_id = "rebuilt-model"
        provider_label = "CPU"
        sample_count = 1
        class_counts = {"类别A": 1}

        def __init__(self, model_dir, cache_path, **kwargs):
            self.cache_path = cache_path

        def forget_label(self, label):
            return 0

        def synchronize(self, samples, progress_callback=None):
            build_started.set()
            release_build.wait(timeout=2)
            self.cache_path.write_text("new-model", encoding="utf-8")

    monkeypatch.setattr(
        manager_module,
        "IncrementalEmbeddingClassifier",
        RebuiltClassifier,
    )
    final_path = project_model_path(tmp_path, "balanced")
    final_path.write_text("old-model", encoding="utf-8")
    old_classifier = FakeConcurrentClassifier()
    manager = _ready_manager(tmp_path, old_classifier)
    try:
        manager.configure_project(
            tmp_path,
            [("a", "a.jpg", "类别A")],
            model_key="balanced",
            force_reinitialize=True,
        )

        assert build_started.wait(timeout=1)
        assert manager._classifier is old_classifier
        assert final_path.read_text(encoding="utf-8") == "old-model"

        release_build.set()
        assert _wait_until(
            lambda: isinstance(manager._classifier, RebuiltClassifier)
        )
        assert final_path.read_text(encoding="utf-8") == "new-model"
        assert not final_path.with_name(
            f".{final_path.stem}.rebuild{final_path.suffix}"
        ).exists()
    finally:
        release_build.set()
        manager.shutdown()


def test_failed_reinitialize_preserves_old_model(monkeypatch, tmp_path):
    class FailingClassifier:
        def __init__(self, model_dir, cache_path, **kwargs):
            self.cache_path = cache_path

        def forget_label(self, label):
            return 0

        def synchronize(self, samples, progress_callback=None):
            self.cache_path.write_text("partial", encoding="utf-8")
            raise RuntimeError("build failed")

    monkeypatch.setattr(
        manager_module,
        "IncrementalEmbeddingClassifier",
        FailingClassifier,
    )
    final_path = project_model_path(tmp_path, "balanced")
    final_path.write_text("old-model", encoding="utf-8")
    old_classifier = FakeConcurrentClassifier()
    manager = _ready_manager(tmp_path, old_classifier)
    try:
        manager.configure_project(
            tmp_path,
            [("a", "a.jpg", "类别A")],
            model_key="balanced",
            force_reinitialize=True,
        )

        assert _wait_until(lambda: not manager._configuration_running)
        assert manager._classifier is old_classifier
        assert manager.is_ready
        assert final_path.read_text(encoding="utf-8") == "old-model"
    finally:
        manager.shutdown()
