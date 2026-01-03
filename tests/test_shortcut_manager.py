import sys
import json
import logging
import pytest

from pathlib import Path

from PySide6 import QtWidgets
from PySide6.QtCore import QSettings

from qv.app import shortcut_manager as sm


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch):
    """QSettings を INI + 一時フォルダに切り替え、テスト間の汚染を防ぐ。"""
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    s = QSettings("TedApp.org", "QV")
    s.clear()
    yield s
    s.clear()


class StubNotifier:
    calls = []

    @classmethod
    def instance(cls):
        return cls

    @classmethod
    def notify(cls, **kwargs):
        cls.calls.append(kwargs)


@pytest.fixture(autouse=True)
def stub_error_notifier(monkeypatch):
    """ErrorNotifier のポップアップを抑止して記録のみ行う。"""
    # shortcut_manager.ErrorNotifier を StubNotifier に差し替える
    monkeypatch.setattr(sm, "ErrorNotifier", StubNotifier)
    StubNotifier.calls.clear()
    yield
    StubNotifier.calls.clear()

@pytest.fixture
def config_dir(tmp_path: Path):
    """ shortcuts.json を一時作成 """
    cfg = tmp_path / "settings"
    cfg.mkdir(parents=True, exist_ok=True)
    defaults = {
        "front_view": "a",
        "back_view": "p",
    }
    (cfg / "shortcuts.json").write_text(json.dumps(defaults), encoding="utf-8")
    return cfg

@pytest.fixture
def main_window(qapp):
    win = QtWidgets.QMainWindow()
    win.setWindowTitle("Test")
    win.show()
    yield win
    win.close()


def text_registers_actions_and_callbacks(qapp, tmp_settings, config_dir, main_window):
    mgr = sm.ShortcutManager(main_window, config_dir)
    assert "front_view" in mgr._actions
    assert mgr._actions["front_view"].shortcut().toString() == "a"

    # コールバック登録
    called = {"front": 0}

    def cb():
        called["front"] += 1

    mgr.add_callback("front_view", cb)
    mgr._on_action_triggered("front_view")
    assert called["front"] == 1


def test_unregistered_shortcut_notifier(qapp, tmp_settings, config_dir, main_window):
    mgr = sm.ShortcutManager(main_window, config_dir)
    mgr._on_action_triggered("nonexistent")
    assert len(StubNotifier.calls) == 1
    note = StubNotifier.calls[0]
    assert note["title"].startswith("Unregistered")
    assert "not registered" in note["msg"]


def test_development_mode_raises_after_notify(qapp, tmp_settings, config_dir, main_window):
    """開発モードでは例外を再送出する"""
    settings_manager = sm.AppSettingsManager()
    settings_manager.set_run_mode("development")
    mgr = sm.ShortcutManager(main_window, config_dir, settings_manager=settings_manager)

    def bad():
        raise RuntimeError("boom")

    mgr.add_callback("front_view", bad)
    with pytest.raises(RuntimeError):
        mgr._on_action_triggered("front_view")
    # Notifier は呼ばれている（その後に再送出）
    assert StubNotifier.calls, "Notifier should be called before re-raise"
    assert "エラー" in StubNotifier.calls[0]["title"] or "Error" in StubNotifier.calls[0]["title"]


def test_production_mode_swallows_and_continues(qapp, tmp_settings, config_dir, main_window):
    """本番モードでは例外を握りつぶして継続する"""
    settings_manager = sm.AppSettingsManager()
    settings_manager.set_run_mode("production")
    mgr = sm.ShortcutManager(main_window, config_dir, settings_manager=settings_manager)

    def bad():
        raise ValueError("bad")

    mgr.add_callback("front_view", bad)
    # 例外はここに留める
    mgr._on_action_triggered("front_view")
    assert StubNotifier.calls, "Notifier shoud be called in production mode"
    # ここまで到達している = 継続している


def test_update_shortcut_conflict(qapp, tmp_settings, config_dir, main_window):
    mgr = sm.ShortcutManager(main_window, config_dir)
    existing = mgr._actions["front_view"].shortcut().toString()
    ok = mgr.update_shortcut("back_view", existing)
    assert ok is False


def test_user_overrides_are_loaded(qapp, tmp_settings, config_dir, main_window):
    s = QSettings("TedApp.org", "QV")
    s.setValue("shortcuts/front_view", "a")
    mgr = sm.ShortcutManager(main_window, config_dir)
    # 登録は大文字でされている。
    assert mgr._actions["front_view"].shortcut().toString() == "A"


def test_info_logging_constains_command_and_callback(
        qapp, tmp_settings, config_dir, main_window, caplog):
    caplog.set_level(logging.INFO, logger=sm.__name__)
    mgr = sm.ShortcutManager(main_window, config_dir)

    def cb():
        pass

    mgr.add_callback("front_view", cb)
    mgr._on_action_triggered("front_view")
    assert "front_view" in caplog.text
    # INFO ログに コマンド名と関数が含まれるはず
    text = caplog.text
    assert "Shortcut triggered: front_view" in text
    assert "cb" in text
