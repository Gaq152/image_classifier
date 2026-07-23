"""更新包完整性标记与持久化脚本测试。"""

import hashlib

from core.update_utils import (
    cleanup_incomplete_updates,
    ensure_persistent_updater,
    load_pending_update,
    load_ready_update,
    save_pending_update,
    save_ready_update,
)


def test_ready_update_requires_marker_and_matching_size(tmp_path):
    """只有完成标记和文件大小一致的更新包才能被识别。"""
    package = tmp_path / "ImageClassifier_v9.9.9.exe"
    payload = b"complete-update-package"
    package.write_bytes(payload)

    assert load_ready_update(tmp_path) is None

    digest = hashlib.sha256(payload).hexdigest()
    save_ready_update(package, "9.9.9", digest, len(payload))
    ready = load_ready_update(tmp_path, verify_hash=True)

    assert ready is not None
    assert ready["version"] == "9.9.9"
    assert ready["path"] == package.resolve()

    package.write_bytes(payload + b"truncated-or-modified")
    assert load_ready_update(tmp_path) is None


def test_cleanup_removes_partial_and_unmarked_packages_but_keeps_ready(tmp_path):
    """启动清理不会把已校验包与中断下载混为一谈。"""
    partial = tmp_path / "ImageClassifier_v9.9.8.exe.part"
    stale = tmp_path / "ImageClassifier_v9.9.8.exe"
    ready_package = tmp_path / "ImageClassifier_v9.9.9.exe"
    partial.write_bytes(b"partial")
    stale.write_bytes(b"unmarked")
    ready_payload = b"ready"
    ready_package.write_bytes(ready_payload)
    save_ready_update(
        ready_package,
        "9.9.9",
        hashlib.sha256(ready_payload).hexdigest(),
        len(ready_payload),
    )

    cleanup_incomplete_updates(tmp_path)

    assert not partial.exists()
    assert not stale.exists()
    assert ready_package.exists()
    assert load_ready_update(tmp_path) is not None


def test_cleanup_keeps_partial_with_persisted_resume_task(tmp_path):
    """启动清理必须保留带任务标记的断点，并删除其他孤立临时文件。"""
    package = tmp_path / "ImageClassifier_v9.9.9.exe"
    partial = package.with_suffix(".exe.part")
    orphan = tmp_path / "ImageClassifier_v9.9.8.exe.part"
    partial.write_bytes(b"downloaded-prefix")
    orphan.write_bytes(b"orphan")
    manifest = {
        "version": "9.9.9",
        "url": "https://example.invalid/ImageClassifier.exe",
        "size_bytes": 100,
        "sha256": "abc",
    }
    save_pending_update(package, "9.9.9", manifest)

    cleanup_incomplete_updates(tmp_path)

    pending = load_pending_update(tmp_path)
    assert pending is not None
    assert pending["downloaded_bytes"] == len(b"downloaded-prefix")
    assert partial.exists()
    assert not orphan.exists()


def test_persistent_updater_never_installs_arbitrary_partial_exe(tmp_path, monkeypatch):
    """手动更新脚本必须先下载 .part、校验并改名，不能扫描任意 exe。"""
    update_dir = tmp_path / "update"
    monkeypatch.setattr("core.update_utils.get_update_dir", lambda: update_dir)
    target = tmp_path / "ImageClassifier.exe"

    batch_path = ensure_persistent_updater(target)
    content = batch_path.read_text(encoding="utf-8")

    assert "$partial=$dest+'.part'" in content
    assert "HASH_MISMATCH" in content
    assert "Move-Item -LiteralPath $partial" in content
    assert 'for %%F in ("%UPDATE_DIR%\\*' not in content
    assert 'if not exist "%NEW_FILE%"' in content
