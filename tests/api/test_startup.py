from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from annotate_tool.api.dependencies import Settings
from annotate_tool.api.main import create_app
from annotate_tool.v2.config import StorageValidationError, V2Paths


def test_validate_writable_probes_every_runtime_directory(tmp_path, monkeypatch):
    paths = V2Paths.from_root(tmp_path / "data")
    opened: list[Path] = []
    original_open = Path.open

    def recording_open(path, *args, **kwargs):
        if path.name.startswith(".write-probe-"):
            opened.append(path.parent)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)

    paths.validate_writable()

    assert set(opened) == {
        paths.root,
        paths.staging,
        paths.catalogs,
        paths.projects,
        paths.exports,
    }
    assert not list(paths.root.rglob(".write-probe-*"))


def test_startup_rejects_unwritable_configured_storage_without_fallback(
    tmp_path, monkeypatch
):
    settings = Settings(
        data_dir=tmp_path / "blocked", frontend_dist=tmp_path / "frontend"
    )
    secret_path = str(settings.data_dir.resolve())

    def deny_probe(_self):
        raise StorageValidationError("Persistent storage is not writable") from PermissionError(
            secret_path
        )

    monkeypatch.setattr(V2Paths, "validate_writable", deny_probe)

    with pytest.raises(
        StorageValidationError, match="Persistent storage is not writable"
    ) as failure:
        with TestClient(create_app(settings)):
            pass

    assert secret_path not in str(failure.value)
    assert not (tmp_path / "workspace_v2").exists()
