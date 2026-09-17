import pytest

from annotate_tool.yolo import box_pixels, parse_label_text, replace_class_token


def test_parse_retains_coordinate_tokens():
    result = parse_label_text("42 0.522 0.433 0.135 0.271\n")

    assert result.problems == ()
    annotation = result.annotations[0]
    assert annotation.class_id == 42
    assert annotation.coordinate_tokens == ("0.522", "0.433", "0.135", "0.271")
    assert annotation.line_index == 0


def test_parser_reports_bad_lines_without_returning_editable_annotations():
    result = parse_label_text("89 0.5 0.5 0.2 0.2\n3 nope 0.5 0.2 0.2\n")

    assert result.annotations == ()
    assert [problem.line_index for problem in result.problems] == [0, 1]


@pytest.mark.parametrize(
    "line",
    [
        "2 0.5 0.5 0 0.2",
        "2 1.1 0.5 0.2 0.2",
        "2 nan 0.5 0.2 0.2",
        "2 0.5 0.5 0.2",
        "two 0.5 0.5 0.2 0.2",
    ],
)
def test_parser_rejects_invalid_yolo_values(line):
    result = parse_label_text(f"{line}\n")

    assert result.annotations == ()
    assert len(result.problems) == 1


def test_parser_ignores_blank_lines_but_preserves_physical_line_index():
    result = parse_label_text("\n3 0.5 0.5 0.2 0.2\n")

    assert result.annotations[0].line_index == 1


def test_box_pixels_clamps_edges_and_uses_floor_ceil():
    annotation = parse_label_text("2 0.10 0.10 0.40 0.40\n").annotations[0]

    assert box_pixels(annotation, (100, 50)) == (0, 0, 30, 15)


def test_replace_class_changes_only_first_token():
    original = "42 0.522 0.433 0.135 0.271\n7 0.1 0.2 0.3 0.4\n"

    updated = replace_class_token(original, 0, "42 0.522 0.433 0.135 0.271", 17)

    assert updated == "17 0.522 0.433 0.135 0.271\n7 0.1 0.2 0.3 0.4\n"


def test_replace_class_preserves_crlf_newlines():
    original = "4 0.5 0.5 0.2 0.2\r\n"

    updated = replace_class_token(original, 0, "4 0.5 0.5 0.2 0.2", 6)

    assert updated == "6 0.5 0.5 0.2 0.2\r\n"


def test_replace_class_rejects_stale_line():
    with pytest.raises(ValueError, match="changed since it was loaded"):
        replace_class_token("3 0.5 0.5 0.2 0.2\n", 0, "4 0.5 0.5 0.2 0.2", 6)


def test_replace_class_rejects_invalid_target_class():
    with pytest.raises(ValueError, match="outside expected range"):
        replace_class_token("3 0.5 0.5 0.2 0.2\n", 0, "3 0.5 0.5 0.2 0.2", 89)
