from __future__ import annotations

from pathlib import Path

from autoapplication.core import updater
from autoapplication.core.updater import (
    INSTALL_FLAGS,
    Release,
    asset_for,
    helper_command,
    install,
    is_newer,
    parse_version,
    repository,
)


def test_parse_version() -> None:
    assert parse_version("v1.2.10") == (1, 2, 10)
    assert parse_version("1.0") == (1, 0, 0)
    assert parse_version("") == ()
    assert parse_version("unbekannt") == ()


def test_is_newer() -> None:
    assert is_newer("0.9.9", "1.0.0")
    assert is_newer("1.0.0", "1.0.1")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("1.2.0", "1.1.9")
    assert is_newer("1.0", "1.0.1")
    assert not is_newer("", "")


def test_repository_override(monkeypatch) -> None:
    assert repository() == "soendi/AutoApplication"
    monkeypatch.setenv("AUTOAPPLICATION_UPDATE_REPO", "jemand/woanders")
    assert repository() == "jemand/woanders"
    assert "jemand/woanders" in updater.api_url()
    assert "jemand/woanders" in updater.feed_url()


def test_asset_for_windows_setup() -> None:
    release = Release(
        version="1.0.0",
        tag="v1.0.0",
        assets={
            "AutoApplication-1.0.0-Setup.exe": "https://example/setup",
            "quatsch.txt": "https://example/txt",
        },
    )
    assert asset_for(release, "win32") == (
        "AutoApplication-1.0.0-Setup.exe",
        "https://example/setup",
    )
    assert asset_for(release, "linux") is None
    assert asset_for(Release(version="1", tag="v1"), "win32") is None


def test_helper_command() -> None:
    command = helper_command(Path("C:/temp/setup.exe"), 1234)
    assert "--apply-update" in command
    assert "--wait-pid" in command
    assert command[-1] == "1234"


def test_install_without_windows(tmp_path) -> None:
    archive = tmp_path / "AutoApplication-1.0.0-Setup.exe"
    archive.write_bytes(b"x")
    result = install(archive)
    if not __import__("sys").platform.startswith("win"):
        assert result.ok is False
        assert "Windows" in result.message


def test_install_missing_file(tmp_path) -> None:
    result = install(tmp_path / "fehlt.exe")
    assert result.ok is False


def test_install_flags_are_silent() -> None:
    assert "/SILENT" in INSTALL_FLAGS
    assert "/CLOSEAPPLICATIONS" in INSTALL_FLAGS
