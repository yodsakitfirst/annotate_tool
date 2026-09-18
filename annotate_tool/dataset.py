from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
import yaml

from annotate_tool.models import (
    AnnotationProblem,
    AssignmentDataset,
    ClassInfo,
    ImageRecord,
    ParseResult,
)
from annotate_tool.yolo import parse_label_text


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PRODUCT_CLASS_COUNT = 89
REVIEW_CLASS_ID = 89
REVIEW_CLASS_NAME = "Needs Review"


class DatasetLoadError(ValueError):
    pass


def _normalize_names(raw_names: Any) -> dict[int, str]:
    if isinstance(raw_names, list):
        keyed_names = dict(enumerate(raw_names))
    elif isinstance(raw_names, dict):
        try:
            keyed_names = {int(key): value for key, value in raw_names.items()}
        except (TypeError, ValueError) as exc:
            raise DatasetLoadError("class IDs in data.yaml must be integers") from exc
    else:
        raise DatasetLoadError("class metadata must contain a names list or dictionary")

    if any(class_id < 0 for class_id in keyed_names):
        raise DatasetLoadError("class IDs in metadata must be nonnegative")
    normalized = {class_id: str(name).strip() for class_id, name in keyed_names.items()}
    if any(not name for name in normalized.values()):
        raise DatasetLoadError("class names cannot be blank")
    return normalized


def _load_class_names(root: Path) -> tuple[dict[int, str], Path | None]:
    yaml_path = root / "data.yaml"
    text_path = root / "classes.txt"
    if yaml_path.is_file():
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise DatasetLoadError(f"could not read data.yaml: {exc}") from exc
        if not isinstance(data, dict) or "names" not in data:
            raise DatasetLoadError("data.yaml must contain a names field")
        return _normalize_names(data["names"]), yaml_path
    if text_path.is_file():
        try:
            names = text_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise DatasetLoadError(f"could not read classes.txt: {exc}") from exc
        return _normalize_names(names), text_path
    return {}, None


def _reference_paths(root: Path) -> dict[int, Path]:
    references = root / "references"
    if not references.is_dir():
        return {}
    found: dict[int, Path] = {}
    for path in sorted(references.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.casefold() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        try:
            class_id = int(path.stem)
        except ValueError:
            continue
        if class_id >= 0 and class_id not in found:
            found[class_id] = path
    return found


def load_assignment(
    root: Path,
    reference_classes: tuple[ClassInfo, ...] | None = None,
) -> AssignmentDataset:
    resolved_root = root.resolve()
    source_class_names, metadata_path = _load_class_names(resolved_root)
    references = _reference_paths(resolved_root)
    if reference_classes is None:
        classes = tuple(
            ClassInfo(class_id, name, references.get(class_id))
            for class_id, name in sorted(source_class_names.items())
        )
    else:
        classes = reference_classes
    problems: list[AnnotationProblem] = []
    images_root = resolved_root / "images"
    labels_root = resolved_root / "labels"
    if not images_root.is_dir():
        raise DatasetLoadError("dataset must contain an images directory")

    image_paths = sorted(
        (
            path
            for path in images_root.rglob("*")
            if path.is_file() and path.suffix.casefold() in SUPPORTED_IMAGE_SUFFIXES
        ),
        key=lambda path: path.relative_to(resolved_root).as_posix().casefold(),
    )
    records: list[ImageRecord] = []
    for image_path in image_paths:
        image_relative = image_path.relative_to(images_root)
        label_path = labels_root / image_relative.with_suffix(".txt")
        relative_path = image_path.relative_to(resolved_root).as_posix()

        image_size: tuple[int, int] | None = None
        image_error: str | None = None
        try:
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                image_size = image.size
        except (OSError, UnidentifiedImageError) as exc:
            image_error = f"could not open image: {exc}"
            problems.append(AnnotationProblem(None, image_error, image_path))

        if label_path.is_file():
            try:
                parsed = parse_label_text(label_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError) as exc:
                parsed = ParseResult((), (AnnotationProblem(None, f"could not read label: {exc}", label_path),))
            label_problems = tuple(
                AnnotationProblem(
                    problem.line_index,
                    f"malformed annotation: {problem.message}",
                    label_path,
                )
                for problem in parsed.problems
            )
            parsed = ParseResult(parsed.annotations, label_problems)
            problems.extend(label_problems)
        else:
            message = "missing label file"
            problem = AnnotationProblem(None, message, label_path)
            parsed = ParseResult((), (problem,))
            problems.append(problem)

        records.append(
            ImageRecord(
                path=image_path,
                relative_path=relative_path,
                label_path=label_path,
                parse_result=parsed,
                image_size=image_size,
                image_error=image_error,
            )
        )

    return AssignmentDataset(
        root=resolved_root,
        classes=classes,
        source_class_names=source_class_names,
        images=tuple(records),
        class_metadata_path=metadata_path,
        problems=tuple(problems),
    )


def source_class_name(dataset: AssignmentDataset, class_id: int) -> str:
    return dataset.source_class_names.get(class_id, f"Unknown source class {class_id}")


def filter_classes(classes: tuple[ClassInfo, ...], query: str) -> tuple[ClassInfo, ...]:
    normalized = query.strip().casefold()
    if not normalized:
        return classes
    if normalized.isdecimal():
        class_id = int(normalized)
        return tuple(item for item in classes if item.class_id == class_id)
    return tuple(item for item in classes if normalized in item.name.casefold())
