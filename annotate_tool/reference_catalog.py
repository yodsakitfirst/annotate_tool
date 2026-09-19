from io import BytesIO
from pathlib import Path, PurePosixPath
import shutil
from zipfile import BadZipFile, ZipFile

from PIL import Image, UnidentifiedImageError
import yaml

from annotate_tool.config import ImportLimits
from annotate_tool.dataset import SUPPORTED_IMAGE_SUFFIXES
from annotate_tool.importer import (
    AssignmentImportError,
    AssignmentStorageError,
    inspect_archive,
)
from annotate_tool.models import ClassInfo


ReferenceClass = ClassInfo


class ReferenceCatalogError(ValueError):
    pass


class ReferenceCatalogStorageError(ReferenceCatalogError):
    pass


def _catalog_names(raw: object) -> dict[int, str]:
    if not isinstance(raw, dict) or not isinstance(raw.get("names"), dict):
        raise ReferenceCatalogError("catalog.yaml must contain a numeric names mapping")
    try:
        names = {int(key): str(value).strip() for key, value in raw["names"].items()}
    except (TypeError, ValueError) as exc:
        raise ReferenceCatalogError("reference class IDs must be numeric") from exc
    if not names or any(class_id < 0 for class_id in names):
        raise ReferenceCatalogError("reference class IDs must be nonnegative numeric values")
    if any(not name for name in names.values()):
        raise ReferenceCatalogError("reference class names cannot be blank")
    return names


def _inspect_catalog(zip_path: Path, limits: ImportLimits) -> tuple[dict[int, str], dict[int, str]]:
    try:
        member_names = inspect_archive(zip_path, limits)
        with ZipFile(zip_path) as archive:
            catalog_members = [name for name in member_names if PurePosixPath(name).as_posix() == "catalog.yaml"]
            if len(catalog_members) != 1:
                raise ReferenceCatalogError("reference catalog must contain catalog.yaml")
            try:
                raw_catalog = yaml.safe_load(archive.read(catalog_members[0]).decode("utf-8"))
            except (UnicodeError, yaml.YAMLError) as exc:
                raise ReferenceCatalogError(f"could not read catalog.yaml: {exc}") from exc
            names = _catalog_names(raw_catalog)
            images: dict[int, str] = {}
            for member_name in member_names:
                path = PurePosixPath(member_name)
                if len(path.parts) != 2 or path.parts[0].casefold() != "references":
                    continue
                if path.suffix.casefold() not in SUPPORTED_IMAGE_SUFFIXES:
                    continue
                try:
                    class_id = int(path.stem)
                except ValueError as exc:
                    raise ReferenceCatalogError("reference image filenames must use numeric class IDs") from exc
                if class_id in images:
                    raise ReferenceCatalogError(f"multiple reference images found for class {class_id}")
                images[class_id] = member_name

            for class_id in images:
                if class_id not in names:
                    raise ReferenceCatalogError(f"reference image class {class_id} has no catalog name")
            for class_id in names:
                if class_id not in images:
                    raise ReferenceCatalogError(f"missing reference image for class {class_id}")

            for class_id, member_name in images.items():
                try:
                    with Image.open(BytesIO(archive.read(member_name))) as image:
                        image.verify()
                except (OSError, UnidentifiedImageError) as exc:
                    raise ReferenceCatalogError(
                        f"unreadable reference image for class {class_id}: {exc}"
                    ) from exc
            return names, images
    except AssignmentStorageError as exc:
        raise ReferenceCatalogStorageError("could not access reference catalog") from exc
    except AssignmentImportError as exc:
        raise ReferenceCatalogError(str(exc)) from exc
    except BadZipFile as exc:
        raise ReferenceCatalogError("could not read reference catalog") from exc
    except OSError as exc:
        raise ReferenceCatalogStorageError("could not access reference catalog") from exc


def import_reference_catalog(
    zip_path: Path,
    destination: Path,
    limits: ImportLimits,
) -> tuple[ReferenceClass, ...]:
    names, images = _inspect_catalog(zip_path, limits)
    if destination.exists():
        raise ReferenceCatalogError(f"reference destination already exists: {destination}")
    image_root = destination / "images"
    destination.mkdir(parents=True)
    image_root.mkdir()
    complete = False
    try:
        with ZipFile(zip_path) as archive:
            for class_id, member_name in images.items():
                suffix = PurePosixPath(member_name).suffix.casefold()
                (image_root / f"{class_id}{suffix}").write_bytes(archive.read(member_name))
        (destination / "catalog.yaml").write_text(
            yaml.safe_dump({"names": names}, sort_keys=True, allow_unicode=True),
            encoding="utf-8",
        )
        (destination / ".catalog_complete").write_text("complete\n", encoding="utf-8")
        complete = True
        return load_reference_catalog(destination)
    finally:
        if not complete and destination.exists():
            shutil.rmtree(destination)


def load_reference_catalog(root: Path) -> tuple[ReferenceClass, ...]:
    catalog_path = root / "catalog.yaml"
    image_root = root / "images"
    try:
        names = _catalog_names(yaml.safe_load(catalog_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ReferenceCatalogError(f"could not read reference catalog: {exc}") from exc
    if not image_root.is_dir():
        raise ReferenceCatalogError("reference catalog images directory is missing")
    image_paths: dict[int, Path] = {}
    for path in sorted(image_root.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.casefold() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        try:
            class_id = int(path.stem)
        except ValueError:
            continue
        if class_id in image_paths:
            raise ReferenceCatalogError(f"multiple reference images found for class {class_id}")
        image_paths[class_id] = path
    classes: list[ReferenceClass] = []
    for class_id, name in sorted(names.items()):
        image_path = image_paths.get(class_id)
        if image_path is None:
            raise ReferenceCatalogError(f"missing reference image for class {class_id}")
        try:
            with Image.open(image_path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            raise ReferenceCatalogError(f"unreadable reference image for class {class_id}: {exc}") from exc
        classes.append(ReferenceClass(class_id, name, image_path))
    return tuple(classes)
