"""Tests for macos_app.py's bundle layout and decisions - not the real
signing, LaunchServices or WebKit behavior, which needs a real Mac app run.
"""

import json
import subprocess

import pytest

from thirtytutors import cli, macos_app

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    python = tmp_path / "base" / "bin" / "python3.11"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")
    venv = tmp_path / "venv"
    (venv / "lib").mkdir(parents=True)
    signed = []
    monkeypatch.setattr(macos_app.sys, "_base_executable", str(python), raising=False)
    monkeypatch.setattr(macos_app.sys, "prefix", str(venv))
    monkeypatch.setattr(macos_app.subprocess, "run", lambda cmd, **kw: signed.append(cmd))
    return tmp_path, python, venv, signed


def test_bundle_has_everything_the_microphone_needs(fake_env):
    tmp_path, python, venv, signed = fake_env
    app = macos_app.ensure_app_bundle(tmp_path / "T.app")
    contents = app / "Contents"
    assert "NSMicrophoneUsageDescription" in (contents / "Info.plist").read_text()
    assert (contents / "MacOS" / "python3").read_bytes() == b"python"
    launcher = (contents / "MacOS" / "ThirtyTutors").read_text()
    assert f"PYTHONHOME={python.parent.parent}" in launcher
    assert f"THIRTYTUTORS_VENV={venv}" in launcher
    assert str(venv / "lib") in (contents / "Resources" / "bootstrap.py").read_text()
    assert not (contents / "pyvenv.cfg").exists()  # codesign refuses it
    assert [cmd[-1] for cmd in signed] == [str(contents / "MacOS" / "python3"), str(app)]


def test_bundle_is_not_rebuilt_while_current(fake_env):
    tmp_path, _, _, signed = fake_env
    macos_app.ensure_app_bundle(tmp_path / "T.app")
    signed.clear()
    macos_app.ensure_app_bundle(tmp_path / "T.app")
    assert signed == []


def test_bundle_is_rebuilt_for_a_different_venv(fake_env, monkeypatch):
    tmp_path, _, venv, signed = fake_env
    app = macos_app.ensure_app_bundle(tmp_path / "T.app")
    signed.clear()
    other = tmp_path / "other"
    (other / "lib").mkdir(parents=True)
    monkeypatch.setattr(macos_app.sys, "prefix", str(other))
    macos_app.ensure_app_bundle(app)
    assert signed
    stamp = json.loads((app / "Contents" / "Resources" / "env_stamp.json").read_text())
    assert stamp["prefix"] == str(other)


def test_shortcut_replaces_old_shortcut_but_not_something_else(tmp_path):
    app = tmp_path / "real.app"
    app.mkdir()
    desktop = tmp_path / "Desktop"
    old = desktop / "ThirtyTutors.app" / "Contents"
    old.mkdir(parents=True)
    (old / "Info.plist").write_text(macos_app.BUNDLE_ID)
    shortcut = macos_app.install_desktop_shortcut(desktop, app)
    assert shortcut.is_symlink()
    assert shortcut.resolve() == app.resolve()

    shortcut.unlink()
    (desktop / "ThirtyTutors.app").mkdir()
    (desktop / "ThirtyTutors.app" / "mine.txt").write_text("keep")
    assert macos_app.install_desktop_shortcut(desktop, app) is None
    assert (desktop / "ThirtyTutors.app" / "mine.txt").exists()


def test_only_the_microphone_for_allowed_hosts_is_granted():
    allowed = {"127.0.0.1"}
    assert macos_app.microphone_decision_grants("127.0.0.1", 1, allowed)
    assert not macos_app.microphone_decision_grants("evil.example", 1, allowed)
    assert not macos_app.microphone_decision_grants("127.0.0.1", 0, allowed)
    assert not macos_app.microphone_decision_grants("127.0.0.1", 2, allowed)


def test_terminal_run_falls_through_when_bundle_cannot_be_built(monkeypatch):
    def fail():
        raise subprocess.CalledProcessError(1, "codesign")

    monkeypatch.setattr(macos_app, "ensure_app_bundle", fail)
    args = cli.build_parser().parse_args([])
    cli._run_in_macos_app_bundle(args)  # returns instead of exiting


def test_terminal_run_exits_after_bundle_closes(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(macos_app, "ensure_app_bundle", lambda: tmp_path)
    monkeypatch.setattr(macos_app, "launch_app_bundle", lambda app, a: (launched.append(a), 0)[1])
    args = cli.build_parser().parse_args(["--port", "9000"])
    with pytest.raises(SystemExit):
        cli._run_in_macos_app_bundle(args)
    assert launched == [["--host", "127.0.0.1", "--port", "9000"]]


def test_venv_python_comes_from_the_bundle_launcher(monkeypatch):
    monkeypatch.delenv("THIRTYTUTORS_VENV", raising=False)
    assert macos_app.venv_python() is None
    monkeypatch.setenv("THIRTYTUTORS_VENV", "/some/venv")
    assert str(macos_app.venv_python()) == "/some/venv/bin/python"
