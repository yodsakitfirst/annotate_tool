from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Annotation:
    class_id: int
    coordinate_tokens: tuple[str, str, str, str]
    coordinates: tuple[float, float, float, float]
    line_index: int
    original_line: str


@dataclass(frozen=True)
class AnnotationProblem:
    line_index: int | None
    message: str
    path: Path | None = None


@dataclass(frozen=True)
class ParseResult:
    annotations: tuple[Annotation, ...]
    problems: tuple[AnnotationProblem, ...]


@dataclass(frozen=True)
class ClassInfo:
    class_id: int
    name: str
    reference_path: Path | None


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    relative_path: str
    label_path: Path
    parse_result: ParseResult
    image_size: tuple[int, int] | None
    image_error: str | None


@dataclass(frozen=True)
class AssignmentDataset:
    root: Path
    classes: tuple[ClassInfo, ...]
    source_class_names: dict[int, str]
    images: tuple[ImageRecord, ...]
    class_metadata_path: Path | None
    problems: tuple[AnnotationProblem, ...]
