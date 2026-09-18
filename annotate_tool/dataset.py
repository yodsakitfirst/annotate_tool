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


def _normalize_names(raw_names: Any) -> tuple[str, ...]:
    if isinstance(raw_names, list):
        names = raw_names
    elif isinstance(raw_names, dict):
        try:
            keyed_names = {int(key): value for key, value in raw_names.items()}
        except (TypeError, ValueError) as exc:
            raise DatasetLoadError("class IDs in data.yaml must be integers") from exc
        if set(keyed_names) not in (set(range(PRODUCT_CLASS_COUNT)), set(range(PRODUCT_CLASS_COUNT + 1))):
            raise DatasetLoadError(
                "class mapping must contain IDs 0 through 88, optionally followed by 89: Needs Review"
            )
        names = [keyed_names[index] for index in range(len(keyed_names))]
    else:
        raise DatasetLoadError("class metadata must contain a names list or dictionary")

    if len(names) not in (PRODUCT_CLASS_COUNT, PRODUCT_CLASS_COUNT + 1):
        raise DatasetLoadError(
            "class mapping must contain 89 product names, optionally followed by Needs Review"
        )
    normalized = tuple(str(name).strip() for name in names)
    if any(not name for name in normalized):
        raise DatasetLoadError("class names cannot be blank")
    if len(normalized) == PRODUCT_CLASS_COUNT + 1 and normalized[REVIEW_CLASS_ID].casefold() != REVIEW_CLASS_NAME.casefold():
        raise DatasetLoadError("class 89 must be named Needs Review")
    return normalized


def _load_class_names(root: Path) -> tuple[tuple[str, ...], Path]:
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
    raise DatasetLoadError("dataset must contain data.yaml or classes.txt")


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
        if 0 <= class_id < 89 and class_id not in found:
            found[class_id] = path
    return found


def load_assignment(root: Path) -> AssignmentDataset:
    resolved_root = root.resolve()
    names, metadata_path = _load_class_names(resolved_root)
    references = _reference_paths(resolved_root)
    classes = tuple(ClassInfo(index, name, references.get(index)) for index, name in enumerate(names))
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
                parsed = parse_label_text(
                    label_path.read_text(encoding="utf-8"),
                    expected_classes=len(names),
                )
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
        images=tuple(records),
        class_metadata_path=metadata_path,
        problems=tuple(problems),
    )


def filter_classes(classes: tuple[ClassInfo, ...], query: str) -> tuple[ClassInfo, ...]:
    normalized = query.strip().casefold()
    if not normalized:
        return classes
    if normalized.isdecimal():
        class_id = int(normalized)
        return tuple(item for item in classes if item.class_id == class_id)
    return tuple(item for item in classes if normalized in item.name.casefold())
