from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import shutil
import stat
import uuid
from zipfile import BadZipFile, ZipFile, ZipInfo

from annotate_tool.config import AppPaths, ImportLimits


@dataclass(frozen=True)
class ImportedAssignment:
    assignment_id: str
    display_name: str
    root: Path
    class_metadata_path: Path


class AssignmentImportError(ValueError):
    pass


def _is_symlink(info: ZipInfo) -> bool:
    return info.create_system == 3 and stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _safe_member_path(name: str) -> PurePosixPath:
    normalized_name = name.replace("\\", "/")
    path = PurePosixPath(normalized_name)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or any(":" in part for part in path.parts)
    ):
        raise AssignmentImportError(f"unsafe archive path: {name}")
    return path


def inspect_archive(zip_path: Path, limits: ImportLimits) -> tuple[str, ...]:
    try:
        with ZipFile(zip_path) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            if len(files) > limits.max_files:
                raise AssignmentImportError("archive contains too many files")
            if sum(info.file_size for info in files) > limits.max_uncompressed_bytes:
                raise AssignmentImportError("archive is too large when uncompressed")

            destinations: set[str] = set()
            names: list[str] = []
            for info in files:
                if _is_symlink(info):
                    raise AssignmentImportError(f"archive contains a symbolic link: {info.filename}")
                safe_path = _safe_member_path(info.filename)
                key = safe_path.as_posix().casefold()
                if key in destinations:
                    raise AssignmentImportError(f"duplicate archive destination: {safe_path.as_posix()}")
                destinations.add(key)
                names.append(safe_path.as_posix())
            return tuple(names)
    except (BadZipFile, OSError) as exc:
        raise AssignmentImportError(f"could not read ZIP archive: {exc}") from exc


def _dataset_root(extraction_root: Path) -> Path:
    if (extraction_root / "images").is_dir():
        return extraction_root

    children = [child for child in extraction_root.iterdir() if child.is_dir()]
    root_files = [child for child in extraction_root.iterdir() if child.is_file()]
    if len(children) == 1 and not root_files and (children[0] / "images").is_dir():
        return children[0]
    raise AssignmentImportError("archive must contain an images directory")


def _wrapper_prefix(member_names: tuple[str, ...]) -> str | None:
    paths = [PurePosixPath(name) for name in member_names]
    if any(path.parts[0].casefold() == "images" for path in paths):
        return None

    first_parts = {path.parts[0] for path in paths}
    if len(first_parts) != 1:
        return None

    candidate = next(iter(first_parts))
    if any(
        len(path.parts) > 1
        and path.parts[0] == candidate
        and path.parts[1].casefold() == "images"
        for path in paths
    ):
        return candidate
    return None


def _metadata_path(dataset_root: Path) -> Path:
    yaml_path = dataset_root / "data.yaml"
    text_path = dataset_root / "classes.txt"
    if yaml_path.is_file():
        return yaml_path
    if text_path.is_file():
        return text_path
    raise AssignmentImportError("archive must contain class metadata in data.yaml or classes.txt")


def ensure_original_backup(assignment_root: Path) -> Path:
    labels = assignment_root / "labels"
    backups = assignment_root / "backups"
    destination = backups / "labels_original"
    marker = backups / ".backup_complete"
    lock = backups / ".backup_lock"
    backups.mkdir(parents=True, exist_ok=True)

    if marker.is_file():
        return destination
    try:
        with lock.open("x", encoding="utf-8"):
            pass
    except FileExistsError as exc:
        raise AssignmentImportError("original-label backup is already being created") from exc

    try:
        if destination.exists():
            raise AssignmentImportError("incomplete original-label backup already exists")
        if labels.is_dir():
            shutil.copytree(labels, destination)
        else:
            destination.mkdir()
        marker.write_text("complete\n", encoding="utf-8")
        return destination
    except Exception:
        if destination.exists() and not marker.exists():
            shutil.rmtree(destination)
        raise
    finally:
        lock.unlink(missing_ok=True)


def import_dataset(
    zip_path: Path,
    display_name: str,
    destination: Path,
    limits: ImportLimits,
) -> Path:
    cleaned_name = display_name.strip()
    if not cleaned_name:
        raise AssignmentImportError("assignment display name is required")

    member_names = inspect_archive(zip_path, limits)
    wrapper_prefix = _wrapper_prefix(member_names)
    if destination.exists():
        raise AssignmentImportError(f"dataset destination already exists: {destination}")
    destination.mkdir(parents=True)
    imported = False

    try:
        with ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                relative = _safe_member_path(info.filename)
                relative_parts = relative.parts
                if wrapper_prefix is not None and relative_parts[0] == wrapper_prefix:
                    relative_parts = relative_parts[1:]
                if not relative_parts:
                    continue
                output_path = destination.joinpath(*relative_parts)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, output_path.open("wb") as output:
                    shutil.copyfileobj(source, output)

        dataset_root = _dataset_root(destination)
        metadata = _metadata_path(dataset_root)
        (dataset_root / "source_name.txt").write_text(f"{cleaned_name}\n", encoding="utf-8")
        ensure_original_backup(dataset_root)
        imported = True
        return metadata
    except AssignmentImportError:
        raise
    except (BadZipFile, OSError) as exc:
        raise AssignmentImportError(f"could not import assignment: {exc}") from exc
    finally:
        if not imported and destination.exists():
            shutil.rmtree(destination)


def import_assignment(
    zip_path: Path,
    display_name: str,
    paths: AppPaths,
    limits: ImportLimits,
) -> ImportedAssignment:
    cleaned_name = display_name.strip()
    if not cleaned_name:
        raise AssignmentImportError("assignment display name is required")
    paths.ensure()
    assignment_id = uuid.uuid4().hex
    final_root = paths.assignments / assignment_id
    metadata = import_dataset(zip_path, cleaned_name, final_root, limits)
    return ImportedAssignment(
        assignment_id=assignment_id,
        display_name=cleaned_name,
        root=final_root,
        class_metadata_path=metadata,
    )
