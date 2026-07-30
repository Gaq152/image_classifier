"""Background orchestration for optional AI-assisted classification."""

import hashlib
import logging
import shutil
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from core.ai import (
    AI_REMOVAL_LABEL,
    DEFAULT_AI_MODEL_KEY,
    IncrementalEmbeddingClassifier,
    get_ai_model_profile,
    project_model_path,
)
from core.ai.feature_extractor import AIModelUnavailableError
from utils.paths import get_ai_cache_dir, get_ai_model_dir


ProjectSample = Tuple[str, str, str]
PredictionRequest = Tuple[int, str, np.ndarray, Tuple[str, ...]]
FeedbackRequest = Tuple[int, Optional[str], Optional[str]]


class _ConfigurationCancelled(Exception):
    pass


class AIClassificationManager(QObject):
    """Own the AI engine and expose only UI-safe signals and methods."""

    status_changed = pyqtSignal(str, str)
    index_progress = pyqtSignal(int, int)
    prediction_ready = pyqtSignal(object)
    model_state_changed = pyqtSignal(object)

    def __init__(
        self,
        preferred_provider: str = "auto",
        logger: Optional[logging.Logger] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.logger = logger or logging.getLogger(__name__)
        self.preferred_provider = preferred_provider
        self._configuration_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ai-configuration"
        )
        self._prediction_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ai-prediction"
        )
        self._feedback_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ai-feedback"
        )
        self._persistence_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ai-persistence"
        )
        self._classifier: Optional[IncrementalEmbeddingClassifier] = None
        self._generation = 0
        self._request_id = 0
        self._latest_request_id = 0
        self._prediction_running = False
        self._queued_prediction: Optional[PredictionRequest] = None
        self._pending_feedback: OrderedDict[str, FeedbackRequest] = OrderedDict()
        self._feedback_running = False
        self._save_timer: Optional[threading.Timer] = None
        self._feedback_revision = 0
        self._saved_revision = 0
        self._lock = threading.RLock()
        self._cache_io_lock = threading.Lock()
        self._closed = False
        self._disabled = False
        self._configuration_running = False
        self._active_model_key = DEFAULT_AI_MODEL_KEY
        self._active_project_dir: Optional[Path] = None

    @staticmethod
    def _legacy_project_cache_path(project_dir: Path) -> Path:
        normalized = str(Path(project_dir)).replace("/", "\\").lower()
        project_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return get_ai_cache_dir() / project_key / "features_v1.npz"

    @property
    def is_ready(self) -> bool:
        """Whether predictions can start immediately without waiting for indexing."""
        with self._lock:
            return (
                not self._closed
                and not self._disabled
                and self._classifier is not None
            )

    @property
    def is_disabled(self) -> bool:
        """Whether AI is unavailable for the active project."""
        with self._lock:
            return self._disabled

    def configure_project(
        self,
        project_dir: Path,
        samples: Sequence[ProjectSample],
        model_key: str = DEFAULT_AI_MODEL_KEY,
        migrate_legacy: bool = False,
        force_reinitialize: bool = False,
        merge_samples: Sequence[ProjectSample] = (),
        excluded_labels: Sequence[str] = (),
    ) -> None:
        profile = get_ai_model_profile(model_key)
        project_dir = Path(project_dir)
        with self._lock:
            if self._closed:
                return
            keep_current_model = bool(
                force_reinitialize
                and self._classifier is not None
                and self._active_project_dir == project_dir
                and self._active_model_key == profile.key
            )
            self._generation += 1
            generation = self._generation
            self._cancel_save_timer_locked()
            self._pending_feedback.clear()
            self._feedback_running = False
            if not keep_current_model:
                self._classifier = None
            self._disabled = False
            self._configuration_running = True
            self._active_model_key = profile.key
            self._active_project_dir = project_dir
        self.status_changed.emit(
            (
                f"正在重新初始化 AI · {profile.display_name}…"
                if force_reinitialize
                else f"正在初始化 AI · {profile.display_name}…"
            ),
            "working",
        )
        self._configuration_executor.submit(
            self._configure_worker,
            generation,
            project_dir,
            tuple(samples),
            profile.key,
            migrate_legacy,
            force_reinitialize,
            tuple(merge_samples),
            tuple(excluded_labels),
        )

    def clear_project(self) -> None:
        with self._lock:
            self._generation += 1
            self._cancel_save_timer_locked()
            self._classifier = None
            self._queued_prediction = None
            self._pending_feedback.clear()
            self._feedback_running = False
            self._configuration_running = False
            self._latest_request_id += 1
            self._disabled = False
            self._active_project_dir = None
        self.status_changed.emit("AI 等待项目数据…", "working")

    def _configure_worker(
        self,
        generation: int,
        project_dir: Path,
        samples: Sequence[ProjectSample],
        model_key: str,
        migrate_legacy: bool,
        force_reinitialize: bool,
        merge_samples: Sequence[ProjectSample],
        excluded_labels: Sequence[str],
    ) -> None:
        rebuild_cache_path: Optional[Path] = None
        try:
            profile = get_ai_model_profile(model_key)
            final_cache_path = project_model_path(project_dir, model_key)
            cache_path = final_cache_path
            if force_reinitialize:
                rebuild_cache_path = final_cache_path.with_name(
                    f".{final_cache_path.stem}.rebuild{final_cache_path.suffix}"
                )
                with self._cache_io_lock:
                    rebuild_cache_path.unlink(missing_ok=True)
                cache_path = rebuild_cache_path
            if (
                migrate_legacy
                and not force_reinitialize
                and model_key == "balanced"
                and not cache_path.exists()
            ):
                legacy_path = self._legacy_project_cache_path(project_dir)
                if legacy_path.exists():
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(legacy_path, cache_path)
            classifier = IncrementalEmbeddingClassifier(
                model_dir=get_ai_model_dir(profile.model_dir_name),
                cache_path=cache_path,
                preferred_provider=self.preferred_provider,
                logger=self.logger,
            )
            removed_count = sum(
                classifier.forget_label(label) for label in excluded_labels
            )
            cached_count = classifier.sample_count
            if samples:
                self.status_changed.emit(
                    f"正在建立 AI 样本库（已有缓存 {cached_count}）…", "working"
                )

                def report_progress(current: int, total: int) -> None:
                    with self._lock:
                        if generation != self._generation or self._closed:
                            raise _ConfigurationCancelled()
                    self.index_progress.emit(current, total)

                with self._cache_io_lock:
                    classifier.synchronize(
                        samples,
                        progress_callback=report_progress,
                    )
            elif merge_samples:
                self.status_changed.emit(
                    f"正在补充 AI 样本库（已有缓存 {cached_count}）…", "working"
                )

                def report_progress(current: int, total: int) -> None:
                    with self._lock:
                        if generation != self._generation or self._closed:
                            raise _ConfigurationCancelled()
                    self.index_progress.emit(current, total)

                with self._cache_io_lock:
                    classifier.merge(
                        merge_samples,
                        progress_callback=report_progress,
                    )
            elif removed_count:
                with self._cache_io_lock:
                    classifier.save()
            elif not cache_path.exists():
                with self._cache_io_lock:
                    classifier.save()

            if force_reinitialize:
                with self._lock:
                    if generation != self._generation or self._closed:
                        raise _ConfigurationCancelled()
                with self._cache_io_lock:
                    cache_path.replace(final_cache_path)
                    classifier.cache_path = final_cache_path

            with self._lock:
                if generation != self._generation or self._closed:
                    return
                self._classifier = classifier
                self._configuration_running = False
                counts = classifier.class_counts
                queued = None
                if not self._prediction_running:
                    queued = self._queued_prediction
                    self._queued_prediction = None
                has_pending_feedback = bool(self._pending_feedback)

            count_text = (
                "，".join(
                    f"{'移除样本' if category == AI_REMOVAL_LABEL else category} {count}"
                    for category, count in sorted(counts.items())
                )
                or "暂无人工样本"
            )
            self.status_changed.emit(
                f"AI 已就绪 · {profile.short_name} · "
                f"{classifier.provider_label} · {count_text}",
                "ready",
            )
            self._emit_model_state(
                classifier,
                project_dir,
                profile.key,
                event=(
                    "reinitialized" if force_reinitialize else "initialized"
                ),
            )
            if queued is not None:
                self._schedule_prediction(queued)
            if has_pending_feedback:
                self._schedule_feedback_if_ready()
        except _ConfigurationCancelled:
            if rebuild_cache_path is not None:
                rebuild_cache_path.unlink(missing_ok=True)
            with self._lock:
                if generation == self._generation:
                    self._configuration_running = False
            self.logger.debug("AI 项目初始化已取消")
        except AIModelUnavailableError as error:
            if rebuild_cache_path is not None:
                rebuild_cache_path.unlink(missing_ok=True)
            with self._lock:
                if generation != self._generation or self._closed:
                    return
                self._configuration_running = False
                using_previous_model = self._classifier is not None
                self._disabled = not using_previous_model
            self.logger.info("AI 辅助未启用: %s", error)
            if using_previous_model:
                self.status_changed.emit(
                    f"AI 重新初始化失败，继续使用旧模型：{error}", "warning"
                )
                self._emit_model_state(
                    self._classifier,
                    project_dir,
                    model_key,
                    event="reinitialize_failed",
                )
                self._schedule_feedback_if_ready()
            else:
                self.status_changed.emit(f"AI 未启用：{error}", "disabled")
        except Exception as error:
            if rebuild_cache_path is not None:
                rebuild_cache_path.unlink(missing_ok=True)
            with self._lock:
                if generation != self._generation or self._closed:
                    return
                self._configuration_running = False
                using_previous_model = self._classifier is not None
                self._disabled = not using_previous_model
            self.logger.exception("AI 初始化失败")
            if using_previous_model:
                self.status_changed.emit(
                    f"AI 重新初始化失败，继续使用旧模型：{error}", "warning"
                )
                self._emit_model_state(
                    self._classifier,
                    project_dir,
                    model_key,
                    event="reinitialize_failed",
                )
                self._schedule_feedback_if_ready()
            else:
                self.status_changed.emit(f"AI 初始化失败：{error}", "error")

    def submit_prediction(
        self,
        image_path: str,
        image_data: np.ndarray,
        categories: Sequence[str],
    ) -> int:
        if not isinstance(image_data, np.ndarray) or image_data.ndim != 3:
            return -1
        with self._lock:
            if self._closed:
                return -1
            if self._disabled:
                return -1
            self._request_id += 1
            request_id = self._request_id
            self._latest_request_id = request_id
            request = (
                request_id,
                str(image_path),
                image_data,
                tuple(categories),
            )
            if self._classifier is None or self._prediction_running:
                self._queued_prediction = request
                return request_id
        self._schedule_prediction(request)
        return request_id

    def _schedule_prediction(self, request: PredictionRequest) -> None:
        with self._lock:
            if self._closed:
                return
            self._prediction_running = True
        self._prediction_executor.submit(self._prediction_worker, request)

    def _prediction_worker(self, request: PredictionRequest) -> None:
        request_id, image_path, image_data, categories = request
        result = None
        try:
            with self._lock:
                classifier = self._classifier
            if classifier is not None:
                result = classifier.predict(
                    request_id=request_id,
                    image_path=image_path,
                    rgb=image_data,
                    categories=categories,
                )
        except Exception as error:
            self.logger.exception("AI 推理失败: %s", image_path)
            self.status_changed.emit(f"AI 推理失败：{error}", "error")
        finally:
            with self._lock:
                is_latest = request_id == self._latest_request_id
                queued = self._queued_prediction
                self._queued_prediction = None
                self._prediction_running = False
            if result is not None and is_latest:
                self.prediction_ready.emit(result)
            if queued is not None:
                self._schedule_prediction(queued)
            else:
                self._schedule_feedback_if_ready()

    def learn(
        self, image_path: str, label: str, actual_path: Optional[str] = None
    ) -> None:
        self._queue_feedback(
            str(image_path),
            str(label),
            str(actual_path) if actual_path else None,
        )

    def forget(self, image_path: str) -> None:
        self._queue_feedback(str(image_path), None, None)

    def _queue_feedback(
        self,
        image_path: str,
        label: Optional[str],
        actual_path: Optional[str],
    ) -> None:
        with self._lock:
            if self._closed or self._active_project_dir is None:
                return
            self._pending_feedback[image_path] = (
                self._generation,
                label,
                actual_path,
            )
            self._pending_feedback.move_to_end(image_path)
        self._schedule_feedback_if_ready()

    def _schedule_feedback_if_ready(self) -> None:
        with self._lock:
            if (
                self._closed
                or self._classifier is None
                or self._configuration_running
                or self._prediction_running
                or self._feedback_running
                or not self._pending_feedback
            ):
                return
            self._feedback_running = True
            generation = self._generation
        self._feedback_executor.submit(self._feedback_worker, generation)

    def _feedback_worker(self, generation: int) -> None:
        changed = False
        classifier = None
        project_dir = None
        model_key = DEFAULT_AI_MODEL_KEY
        while True:
            with self._lock:
                if generation != self._generation or self._closed:
                    if generation == self._generation:
                        self._feedback_running = False
                    break
                if self._prediction_running or not self._pending_feedback:
                    self._feedback_running = False
                    break
                image_path, request = self._pending_feedback.popitem(last=False)
                request_generation, label, actual_path = request
                if request_generation != generation:
                    continue
                classifier = self._classifier
                project_dir = self._active_project_dir
                model_key = self._active_model_key
            if classifier is None:
                break
            try:
                if label is None:
                    changed = classifier.forget(image_path) or changed
                else:
                    changed = (
                        classifier.learn(
                            image_path,
                            label,
                            actual_path=actual_path,
                        )
                        or changed
                    )
            except Exception:
                self.logger.exception("AI 增量学习失败: %s", image_path)

        if changed and classifier is not None and project_dir is not None:
            self._schedule_debounced_save(
                generation,
                classifier,
                project_dir,
                model_key,
            )

    def _schedule_debounced_save(
        self,
        generation: int,
        classifier: IncrementalEmbeddingClassifier,
        project_dir: Path,
        model_key: str,
    ) -> None:
        with self._lock:
            if generation != self._generation or self._closed:
                return
            self._feedback_revision += 1
            revision = self._feedback_revision
            self._cancel_save_timer_locked()
            timer = threading.Timer(
                0.5,
                self._submit_save,
                args=(
                    generation,
                    revision,
                    classifier,
                    project_dir,
                    model_key,
                ),
            )
            timer.daemon = True
            self._save_timer = timer
            timer.start()

    def _cancel_save_timer_locked(self) -> None:
        timer = self._save_timer
        self._save_timer = None
        if timer is not None:
            timer.cancel()

    def _submit_save(
        self,
        generation: int,
        revision: int,
        classifier: IncrementalEmbeddingClassifier,
        project_dir: Path,
        model_key: str,
    ) -> None:
        with self._lock:
            if generation != self._generation or self._closed:
                return
            self._save_timer = None
        self._persistence_executor.submit(
            self._save_worker,
            generation,
            revision,
            classifier,
            project_dir,
            model_key,
        )

    def _save_worker(
        self,
        generation: int,
        revision: int,
        classifier: IncrementalEmbeddingClassifier,
        project_dir: Path,
        model_key: str,
    ) -> None:
        try:
            with self._lock:
                if generation != self._generation or self._closed:
                    return
            with self._cache_io_lock:
                with self._lock:
                    if generation != self._generation or self._closed:
                        return
                classifier.save()
            with self._lock:
                if generation != self._generation or self._closed:
                    return
                self._saved_revision = max(self._saved_revision, revision)
            self._emit_model_state(classifier, project_dir, model_key)
        except Exception:
            self.logger.exception("AI 样本库保存失败")

    def _emit_model_state(
        self,
        classifier: IncrementalEmbeddingClassifier,
        project_dir: Path,
        model_key: str,
        event: str = "updated",
    ) -> None:
        """Publish a serializable snapshot for classification_state.json."""
        profile = get_ai_model_profile(model_key)
        self.model_state_changed.emit(
            {
                "project_dir": str(project_dir),
                "model_key": model_key,
                "model_id": classifier.model_id,
                "project_model_file": profile.project_model_file,
                "sample_count": classifier.sample_count,
                "class_counts": classifier.class_counts,
                "provider": classifier.provider_label,
                "event": event,
            }
        )

    def shutdown(self) -> None:
        with self._lock:
            classifier = self._classifier
            needs_save = self._feedback_revision > self._saved_revision
            self._cancel_save_timer_locked()
            self._closed = True
            self._generation += 1
            self._queued_prediction = None
            self._pending_feedback.clear()
        if classifier is not None and needs_save:
            self._persistence_executor.submit(classifier.save)
        self._configuration_executor.shutdown(wait=False, cancel_futures=True)
        self._prediction_executor.shutdown(wait=False, cancel_futures=True)
        self._feedback_executor.shutdown(wait=False, cancel_futures=True)
        self._persistence_executor.shutdown(wait=False, cancel_futures=False)
