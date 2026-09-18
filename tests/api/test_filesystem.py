from pathlib import Path
import shutil

import pytest

from annotate_tool.v2.filesystem import publish_directory


def test_publish_directory_falls_back_when_windows_denies_rename(tmp_path, monkeypatch):
    staging_parent = tmp_path / "staging"
    final_parent = tmp_path / "catalogs"
    source = staging_parent / "item"
    destination = final_parent / "item"
    source.mkdir(parents=True)
    final_parent.mkdir()
    (source / "payload.txt").write_text("complete", encoding="utf-8")

    def deny_rename(_source, _destination):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(Path, "replace", deny_rename)

    publish_directory(source, destination, staging_parent, final_parent)

    assert not source.exists()
    assert (destination / "payload.txt").read_text(encoding="utf-8") == "complete"


def test_publish_directory_removes_partial_destination_when_fallback_copy_fails(tmp_path, monkeypatch):
    staging_parent = tmp_path / "staging"
    final_parent = tmp_path / "projects"
    source = staging_parent / "item"
    destination = final_parent / "item"
    source.mkdir(parents=True)
    final_parent.mkdir()
    (source / "payload.txt").write_text("complete", encoding="utf-8")
    monkeypatch.setattr(Path, "replace", lambda *_args: (_ for _ in ()).throw(PermissionError(5, "denied")))

    def partial_copy(_source, target):
        Path(target).mkdir()
        (Path(target) / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("copy failed")

    monkeypatch.setattr(shutil, "copytree", partial_copy)

    with pytest.raises(OSError, match="copy failed"):
        publish_directory(source, destination, staging_parent, final_parent)

    assert source.exists()
    assert not destination.exists()
