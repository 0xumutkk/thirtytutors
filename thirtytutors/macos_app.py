"""macOS app bundle and microphone support for the desktop window.

WKWebView only exposes navigator.mediaDevices when the running app's own
Info.plist has NSMicrophoneUsageDescription, and a bare Python interpreter has
no Info.plist. A launcher script inside a .app isn't enough either: macOS
works out the main bundle from the executable's path, so once the script execs
the venv's python the bundle is gone. So ensure_app_bundle puts a real copy of
the interpreter in Contents/MacOS, with a launcher pointing it at the base
Python's stdlib (PYTHONHOME) and a bootstrap script adding the venv's packages.
A pyvenv.cfg can't do this job, because codesign refuses a bundle with one next
to the executable or in Contents. sys.prefix is therefore the base Python, not
the venv, so anything that must act on the venv uses venv_python().

The bundle lives in DATA_DIR rather than the venv, with the Desktop shortcut
symlinking to it. Rebuilding changes its ad-hoc signature, and macOS asks for
microphone permission again, so it's only rebuilt when its stamp goes stale.

pywebview has no handler for WebKit's capture permission request either, which
leaves getUserMedia pending forever - install_microphone_permission_handler
adds one. A capture request also waits until the window has focus, and an app
started from a terminal doesn't always get it, hence activate_app.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .constants import DATA_DIR

BUNDLE_ID = "com.wissam.thirtytutors"
APP_BUNDLE_DIR = DATA_DIR / "ThirtyTutors.app"
APP_LOG_FILE = DATA_DIR / "app.log"

_INFO_PLIST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0">\n<dict>\n'
    "  <key>CFBundleName</key><string>ThirtyTutors</string>\n"
    "  <key>CFBundleExecutable</key><string>ThirtyTutors</string>\n"
    "  <key>CFBundleIconFile</key><string>ThirtyTutors.icns</string>\n"
    f"  <key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>\n"
    "  <key>CFBundlePackageType</key><string>APPL</string>\n"
    "  <key>CFBundleShortVersionString</key><string>1.0</string>\n"
    "  <key>NSMicrophoneUsageDescription</key>"
    "<string>ThirtyTutors listens to your voice during lessons.</string>\n"
    "</dict>\n</plist>\n"
)
_VENV_ENV_VAR = "THIRTYTUTORS_VENV"

# WKMediaCaptureType's value for microphone-only requests.
_MEDIA_CAPTURE_MICROPHONE = 1


def running_in_app_bundle() -> bool:
    return ".app/Contents/MacOS/" in sys.executable


def bundle_launcher() -> Path:
    return Path(sys.executable).parent / "ThirtyTutors"


def venv_python() -> Path | None:
    """The venv's own interpreter when running inside the bundle."""
    venv = os.environ.get(_VENV_ENV_VAR)
    return Path(venv) / "bin" / "python" if venv else None


def _launcher_script(base_python: Path) -> str:
    return (
        "#!/bin/bash\n"
        f"export PYTHONHOME={shlex.quote(str(base_python.parent.parent))}\n"
        f"export {_VENV_ENV_VAR}={shlex.quote(sys.prefix)}\n"
        'here="$(dirname "$0")"\n'
        'exec "$here/python3" "$here/../Resources/bootstrap.py" "$@"\n'
    )


def _bootstrap_script() -> str:
    site_packages = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    # addsitedir rather than PYTHONPATH: it also processes .pth files, which is
    # how an editable install is found.
    return f'import runpy, site\nsite.addsitedir({str(site_packages)!r})\nrunpy.run_module("thirtytutors", run_name="__main__", alter_sys=True)\n'


def _base_python() -> Path:
    return Path(getattr(sys, "_base_executable", sys.executable)).resolve()


def _bundle_stamp(base_python: Path) -> str:
    return json.dumps(
        {
            "prefix": sys.prefix,
            "python": str(base_python),
            "python_mtime": base_python.stat().st_mtime,
            "plist": _INFO_PLIST,
            "launcher": _launcher_script(base_python),
            "bootstrap": _bootstrap_script(),
        }
    )


def ensure_app_bundle(app_dir: Path = APP_BUNDLE_DIR) -> Path:
    """Builds the app bundle for the running venv, unless an up-to-date one is
    already there. Raises OSError/CalledProcessError if it can't."""
    base_python = _base_python()
    stamp = _bundle_stamp(base_python)
    stamp_file = app_dir / "Contents" / "Resources" / "env_stamp.json"
    if stamp_file.is_file() and stamp_file.read_text(encoding="utf-8") == stamp:
        return app_dir

    if app_dir.exists():
        shutil.rmtree(app_dir)
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir()

    python_copy = macos_dir / "python3"
    shutil.copy2(base_python, python_copy)
    launcher = macos_dir / "ThirtyTutors"
    launcher.write_text(_launcher_script(base_python), encoding="utf-8")
    launcher.chmod(0o755)
    (contents / "Info.plist").write_text(_INFO_PLIST, encoding="utf-8")
    (resources_dir / "bootstrap.py").write_text(_bootstrap_script(), encoding="utf-8")
    icon = Path(__file__).parent / "static" / "ThirtyTutors.icns"
    if icon.is_file():
        shutil.copy2(icon, resources_dir / "ThirtyTutors.icns")
    stamp_file.write_text(stamp, encoding="utf-8")

    # Inside first, then the bundle - copying invalidated python's signature.
    subprocess.run(["codesign", "--force", "-s", "-", str(python_copy)], check=True, capture_output=True)
    subprocess.run(["codesign", "--force", "-s", "-", str(app_dir)], check=True, capture_output=True)
    return app_dir


def install_desktop_shortcut(desktop_dir: Path, app_dir: Path) -> Path | None:
    """Points Desktop/ThirtyTutors.app at the bundle. Replaces an earlier
    shortcut, but never something else that happens to have this name -
    returns None in that case."""
    shortcut = desktop_dir / "ThirtyTutors.app"
    if shortcut.is_symlink():
        shortcut.unlink()
    elif shortcut.exists():
        plist = shortcut / "Contents" / "Info.plist"
        if not plist.is_file() or BUNDLE_ID not in plist.read_text(encoding="utf-8", errors="replace"):
            return None
        shutil.rmtree(shortcut)
    shortcut.symlink_to(app_dir)
    return shortcut


def launch_app_bundle(app_dir: Path, args: list[str]) -> int:
    """Opens the bundle through LaunchServices and waits for it to close.
    `open` is what makes macOS treat the bundle as the app asking for the
    microphone; run from a terminal directly, the terminal would be."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = str(APP_LOG_FILE)
    return subprocess.run(["open", "-W", "-n", str(app_dir), "--stdout", log, "--stderr", log, "--args", *args]).returncode


def microphone_decision_grants(host: str | None, media_type: int, allowed_hosts: set[str]) -> bool:
    return media_type == _MEDIA_CAPTURE_MICROPHONE and host in allowed_hosts


def install_microphone_permission_handler(allowed_hosts: set[str]) -> None:
    """Answers WebKit's capture requests: the microphone for this app's own
    server, nothing for anything else. macOS's own permission still applies."""
    import objc
    import WebKit
    from webview.platforms.cocoa import BrowserView

    class BrowserDelegate(objc.Category(BrowserView.BrowserDelegate)):
        def webView_requestMediaCapturePermissionForOrigin_initiatedByFrame_type_decisionHandler_(
            self, webview, origin, frame, media_type, decision_handler
        ):
            granted = microphone_decision_grants(str(origin.host()), int(media_type), allowed_hosts)
            decision_handler(WebKit.WKPermissionDecisionGrant if granted else WebKit.WKPermissionDecisionDeny)


def activate_app() -> None:
    """webview.start() func - runs on its own thread once the window is up."""
    import AppKit
    from PyObjCTools import AppHelper

    AppHelper.callAfter(lambda: AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True))
