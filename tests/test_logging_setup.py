import sys
import time
import logging
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_logging():
    """
    各テストの前後で logging 初期化して汚染を防ぐ
    """
    yield
    # すべてのハンドラを閉じて root を初期状態へ
    logging.shutdown()
    # 念のため root のハンドラも除去
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


@pytest.fixture
def tmp_log_dir(tmp_path: Path):
    d = tmp_path / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def module(tmp_log_dir, monkeypatch):
    """
    logging_setup をクリーンにimport し直し、
    default_log_dir をテンポラリディレクトリへ向ける
    :param tmp_log_dir:
    :param monkeypatch:
    :return: logging_setup
    """
    if "logging_setup" in sys.modules:
        del sys.modules["logging_setup"]
    from app import logging_setup
    # default_log_dir(app_name) -> tmp_log_dir
    monkeypatch.setattr(logging_setup, "default_log_dir", lambda app_name: tmp_log_dir)
    return logging_setup


def _read_text(path: Path) -> str:
    " macOS等での同時書き出しに備え、短いリトライを入れる"
    for _ in range(10):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            time.sleep(0.02)
    # 無理なら諦める
    return path.read_text(encoding="utf-8", errors="replace")


def test_info_level_writes_file(module, tmp_log_dir):
    """test at INFO level"""
    logs = module.LogSystem.from_levels("qv", root_level=logging.INFO, console_level=logging.INFO)
    logger = logging.getLogger("qv.test")

    logger.debug("debug should NOT appear")
    logger.info("info should appear")
    logger.warning("warning should appear")
    logs.stop()  # フラッシュ

    log_file = tmp_log_dir / "qv.log"
    assert log_file.exists(), "ログファイルが作成されていません"

    text = _read_text(log_file)
    assert "info should appear" in text
    assert "warning should appear" in text
    assert "debug should NOT appear" not in text

    assert " INFO " in text or " WARNING " in text
    assert "qv.test" in text


def test_debug_level_outputs_debug(module, tmp_log_dir):
    """test at DEBUG level"""
    logs = module.LogSystem.from_levels("qv", root_level=logging.DEBUG, console_level=logging.DEBUG)
    logger = logging.getLogger("qv.clipping")

    logger.debug("debug visible")
    logger.info("info visible")
    logs.stop()

    text = _read_text(tmp_log_dir / "qv.log")
    assert "debug visible" in text
    assert "info visible" in text


def test_queue_listener_flush_on_stop(module, tmp_log_dir):
    logs = module.LogSystem.from_levels("qv", root_level=logging.INFO, console_level=logging.INFO)
    logger = logging.getLogger("qv.bulk")

    for i in range(200):
        logger.info("line %04d", i)

    # stop() で QueueListener がフラッシュして終了すること
    logs.stop()

    text = _read_text(tmp_log_dir / "qv.log")

    assert "line 0000" in text
    assert "line 0099" in text
    assert "line 0199" in text
    assert "line 0200" not in text

    assert text.count("qv.bulk") >= 150


def text_rotation_by_small_max_bytes(module, tmp_log_dir, monkeypatch):
    """
    build_config の _file_settings.maxBytes をモンキーパッチして、
    ローテーションを強制的に発生させる
    :param module:
    :param tmp_log_dir:
    :param monkeypatch:
    :return: NOne
    """
    monkeypatch.setenv("QV_LOG_BACKUP_COUNT", "2")

    # build_config をらっぷして maxBytes を小さくsルウ
    orig_build = module.build_config

    def tiny_build_config(app_name: str, root_level: int, console_level: int, log_dir: Path | None = None):
        cfg = orig_build(app_name, root_level, console_level, log_dir)
        cfg["_file_settings"]["maxBytes"] = 100  # 小容量に設定
        return cfg

    monkeypatch.setattr(module, "build_config", tiny_build_config)

    logs = module.LogSystem.from_levels("qv", root_level=logging.INFO, console_level=logging.INFO)
    logger = logging.getLogger("qv.rotate")

    payload = "X" * 180
    for i in range(200):
        logger.info("i=%03d %s", i, payload)

    logs.stop()

    base = tmp_log_dir / "qv.log"
    rot1 = tmp_log_dir / "qv.log.1"
    rot2 = tmp_log_dir / "qv.log.2"

    assert base.exists()
    assert rot1.exists() or rot2.exists()

    # いずれのファイルに、最初と最後の数字が分散している想定でチェックする
    text_all = ""
    for p in [base, rot1, rot2]:
        if p.exists():
            text_all += _read_text(p)
    assert "i=000" in text_all
    assert "i=199" in text_all
