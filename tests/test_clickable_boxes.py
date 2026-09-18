from PIL import Image

from annotate_tool.clickable_boxes import build_clickable_image_payload, clicked_object_index
from annotate_tool.workflow import ObjectKey
from annotate_tool.yolo import parse_label_text


def annotations():
    return parse_label_text("3 0.5 0.5 0.2 0.2\n7 0.2 0.25 0.1 0.2\n").annotations


def test_payload_uses_original_pixel_space_and_line_ids():
    payload = build_clickable_image_payload(
        Image.new("RGB", (100, 80), "black"),
        annotations(),
        selected_line_index=0,
    )

    assert payload["width"] == 100
    assert payload["height"] == 80
    assert payload["boxes"][0] == {
        "line_index": 0,
        "number": 1,
        "x": 40,
        "y": 32,
        "width": 20,
        "height": 16,
        "selected": True,
    }
    assert payload["image_base64"].startswith("iVBOR")


def test_clicked_line_selects_object_on_current_image(tmp_path):
    first, second = annotations()
    objects = (
        ObjectKey(0, "images/a.jpg", tmp_path / "a.txt", 0, first),
        ObjectKey(2, "images/c.jpg", tmp_path / "c.txt", 1, second),
    )

    assert clicked_object_index(objects, image_index=2, line_index=1) == 1
    assert clicked_object_index(objects, image_index=2, line_index=99) is None
    assert clicked_object_index(objects, image_index=0, line_index=1) is None
