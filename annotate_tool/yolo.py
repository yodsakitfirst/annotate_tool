import math
import re
from collections.abc import Collection

from annotate_tool.models import Annotation, AnnotationProblem, ParseResult


def parse_label_text(text: str, expected_classes: int | None = None) -> ParseResult:
    annotations: list[Annotation] = []
    problems: list[AnnotationProblem] = []

    for line_index, physical_line in enumerate(text.splitlines()):
        original_line = physical_line.strip()
        if not original_line:
            continue

        tokens = original_line.split()
        try:
            if len(tokens) != 5:
                raise ValueError("expected five YOLO fields")
            class_id = int(tokens[0])
            if class_id < 0:
                raise ValueError("class ID must be nonnegative")
            if expected_classes is not None and class_id >= expected_classes:
                raise ValueError(f"class ID {class_id} is outside expected range 0-{expected_classes - 1}")
            coordinates = tuple(float(token) for token in tokens[1:])
            if not all(math.isfinite(value) for value in coordinates):
                raise ValueError("coordinates must be finite numbers")
            x_center, y_center, width, height = coordinates
            if not 0 <= x_center <= 1 or not 0 <= y_center <= 1:
                raise ValueError("box center must be within 0-1")
            if not 0 < width <= 1 or not 0 < height <= 1:
                raise ValueError("box width and height must be within 0-1")
        except (TypeError, ValueError) as exc:
            problems.append(AnnotationProblem(line_index, str(exc)))
            continue

        annotations.append(
            Annotation(
                class_id=class_id,
                coordinate_tokens=(tokens[1], tokens[2], tokens[3], tokens[4]),
                coordinates=(x_center, y_center, width, height),
                line_index=line_index,
                original_line=original_line,
            )
        )

    return ParseResult(tuple(annotations), tuple(problems))


def box_pixels(annotation: Annotation, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    image_width, image_height = image_size
    x_center, y_center, width, height = annotation.coordinates
    left = math.floor((x_center - width / 2) * image_width)
    top = math.floor((y_center - height / 2) * image_height)
    right = math.ceil((x_center + width / 2) * image_width - 1e-9)
    bottom = math.ceil((y_center + height / 2) * image_height - 1e-9)
    return (
        max(0, min(image_width, left)),
        max(0, min(image_height, top)),
        max(0, min(image_width, right)),
        max(0, min(image_height, bottom)),
    )


def replace_class_token(
    text: str,
    line_index: int,
    expected_line: str,
    new_class_id: int,
    expected_classes: int = 89,
    allowed_class_ids: Collection[int] | None = None,
) -> str:
    if allowed_class_ids is not None and new_class_id not in frozenset(allowed_class_ids):
        raise ValueError(f"class ID {new_class_id} is not in the project reference catalog")
    if allowed_class_ids is None and not 0 <= new_class_id < expected_classes:
        raise ValueError(f"class ID {new_class_id} is outside expected range 0-{expected_classes - 1}")

    lines = text.splitlines(keepends=True)
    if line_index < 0 or line_index >= len(lines):
        raise ValueError("annotation line no longer exists")

    current_line = lines[line_index]
    current_content = current_line.rstrip("\r\n")
    if current_content.strip() != expected_line.strip():
        raise ValueError("annotation changed since it was loaded")

    token_match = re.search(r"\S+", current_content)
    if token_match is None:
        raise ValueError("annotation line is empty")
    lines[line_index] = (
        current_content[: token_match.start()]
        + str(new_class_id)
        + current_content[token_match.end() :]
        + current_line[len(current_content) :]
    )
    return "".join(lines)
