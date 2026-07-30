"""Interaction tests for automatic/manual AI prediction controls."""

from pathlib import Path

import numpy as np
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QMainWindow

from ui.main_window import ImageClassifier


class PredictionWindowHarness(ImageClassifier):
    """Small QMainWindow harness that reuses the production Tab interception."""

    def __init__(self):
        QMainWindow.__init__(self)
        self.ai_prediction_mode = "manual"
        self.manual_prediction_count = 0
        self.input_mode = False

    def _is_in_input_mode(self):
        return self.input_mode

    def trigger_manual_ai_prediction(self):
        self.manual_prediction_count += 1


class ImageLabelSpy:
    def __init__(self):
        self.image = None

    def set_image(self, image):
        self.image = image


class CachedImageDisplayHarness(ImageClassifier):
    """Capture the image forwarded by the cache-display path."""

    def __init__(self):
        QMainWindow.__init__(self)
        self.image_label = ImageLabelSpy()
        self.ai_ready_data = None

    def _on_ai_image_ready(self, image_data):
        self.ai_ready_data = image_data


def test_tab_triggers_prediction_only_in_manual_non_input_mode(qtbot):
    window = PredictionWindowHarness()
    qtbot.addWidget(window)

    assert window.focusNextPrevChild(True)
    assert window.manual_prediction_count == 1

    window.ai_prediction_mode = "auto"
    window.focusNextPrevChild(True)
    assert window.manual_prediction_count == 1

    window.ai_prediction_mode = "manual"
    window.input_mode = True
    window.focusNextPrevChild(True)
    assert window.manual_prediction_count == 1


def test_cached_pixmap_display_is_forwarded_to_ai(qtbot):
    window = CachedImageDisplayHarness()
    qtbot.addWidget(window)
    pixmap = QPixmap(5, 4)
    pixmap.fill(QColor(12, 34, 56))

    window.display_image(pixmap, Path("cached.jpg"))

    assert window.image_label.image is pixmap
    assert window.ai_ready_data is pixmap


def test_qpixmap_is_converted_to_rgb_array_for_ai(qtbot):
    pixmap = QPixmap(5, 4)
    pixmap.fill(QColor(12, 34, 56))

    rgb = ImageClassifier._coerce_ai_rgb_image(None, pixmap)

    assert rgb.shape == (4, 5, 3)
    assert rgb.dtype == np.uint8
    assert np.all(rgb == np.array([12, 34, 56], dtype=np.uint8))
