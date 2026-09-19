import io
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import tarfile
import uuid

import pytest


REPOSITORY_ROOT = Path(__file__).parents[1]


def _bash_executable() -> str | None:
    discovered = shutil.which("bash")
    if discovered:
        return discovered
    git_bash = Path(r"C:\Program Files\Git\usr\bin\bash.exe")
    return str(git_bash) if git_bash.is_file() else None


BASH = _bash_executable()
pytestmark = pytest.mark.skipif(
    os.name == "nt" or BASH is None,
    reason="deployment scripts require a POSIX host",
)


@pytest.fixture
def deployment_tmp_path(tmp_path):
    if os.name != "nt":
        yield tmp_path
        return
    local_tmp = REPOSITORY_ROOT / "tmp" / "deployment-tests" / uuid.uuid4().hex
    local_tmp.mkdir(parents=True)
    try:
        yield local_tmp
    finally:
        shutil.rmtree(local_tmp, ignore_errors=True)


def _shell_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return resolved.as_posix()
    drive = resolved.drive.rstrip(":").lower()
    remainder = resolved.as_posix()[2:].lstrip("/")
    return f"/{drive}/{remainder}"


def run_script(name: str, *args: Path) -> subprocess.CompletedProcess[str]:
    script = REPOSITORY_ROOT / "scripts" / name
    assert script.is_file(), f"deployment script is missing: {script}"
    command = " ".join(
        [
            "cd",
            shlex.quote(_shell_path(REPOSITORY_ROOT)),
            "&&",
            "sh",
            shlex.quote(f"scripts/{name}"),
            *(shlex.quote(_shell_path(path)) for path in args),
        ]
    )
    return subprocess.run(
        [BASH, "-lc", command],
        text=True,
        capture_output=True,
        check=False,
    )


def test_backup_restore_round_trip(deployment_tmp_path):
    data = deployment_tmp_path / "data"
    (data / "projects" / "p1").mkdir(parents=True)
    (data / "app.sqlite3").write_bytes(b"sqlite")
    (data / "projects" / "p1" / "labels.txt").write_text(
        "immutable\n", encoding="utf-8"
    )
    backups = deployment_tmp_path / "backups"

    saved = run_script("backup.sh", data, backups)

    assert saved.returncode == 0, saved.stderr
    archives = list(backups.glob("annotation-desk-*.tar.gz"))
    assert len(archives) == 1
    restored = deployment_tmp_path / "restored"

    result = run_script("restore.sh", archives[0], restored)

    assert result.returncode == 0, result.stderr
    assert (restored / "app.sqlite3").read_bytes() == b"sqlite"
    assert (restored / "projects" / "p1" / "labels.txt").read_text(
        encoding="utf-8"
    ) == "immutable\n"


def test_backup_rejects_destination_inside_data_root(deployment_tmp_path):
    data = deployment_tmp_path / "data"
    data.mkdir()

    result = run_script("backup.sh", data, data / "backups")

    assert result.returncode != 0
    assert not list(data.rglob("*.tar.gz"))


def test_restore_refuses_nonempty_target(deployment_tmp_path):
    target = deployment_tmp_path / "data"
    target.mkdir()
    (target / "keep").write_text("keep", encoding="utf-8")
    archive = deployment_tmp_path / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        content = b"sqlite"
        member = tarfile.TarInfo("app.sqlite3")
        member.size = len(content)
        output.addfile(member, io.BytesIO(content))

    result = run_script("restore.sh", archive, target)

    assert result.returncode != 0
    assert (target / "keep").read_text(encoding="utf-8") == "keep"


def test_restore_rejects_parent_traversal_before_creating_target(deployment_tmp_path):
    archive = deployment_tmp_path / "malicious.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        content = b"escape"
        member = tarfile.TarInfo("../outside")
        member.size = len(content)
        output.addfile(member, io.BytesIO(content))
    target = deployment_tmp_path / "restored"

    result = run_script("restore.sh", archive, target)

    assert result.returncode != 0
    assert not target.exists()
    assert not (deployment_tmp_path / "outside").exists()
