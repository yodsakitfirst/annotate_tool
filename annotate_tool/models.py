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
