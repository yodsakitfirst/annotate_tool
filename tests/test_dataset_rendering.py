from pathlib import Path

from PIL import Image
import pytest
import yaml

from annotate_tool.dataset import DatasetLoadError, filter_classes, load_assignment
from annotate_tool.rendering import crop_annotation, draw_numbered_boxes, reference_placeholder


def test_load_assignment_maps_images_labels_classes_and_references(dataset_root):
    dataset = load_assignment(dataset_root)

    assert len(dataset.classes) == 89
    assert dataset.classes[3].name == "Product 03"
    assert dataset.classes[3].reference_path.name == "3.jpg"
    assert dataset.classes[17].reference_path.name == "17.png"
    assert dataset.classes[4].reference_path is None
    assert dataset.images[0].relative_path == "images/a.jpg"
    assert len(dataset.images[0].parse_result.annotations) == 2


def test_search_matches_name_and_exact_numeric_id(dataset_root):
    classes = load_assignment(dataset_root).classes

    assert [item.class_id for item in filter_classes(classes, "product 08")] == [8]
    assert [item.class_id for item in filter_classes(classes, "17")] == [17]
    assert filter_classes(classes, "not-a-product") == ()


def test_crop_matches_box_with_clamped_padding(dataset_root):
    record = load_assignment(dataset_root).images[0]

    with Image.open(record.path) as image:
        crop = crop_annotation(image, record.parse_result.annotations[0], padding_ratio=0)

    assert crop.size == (20, 16)


def test_overlay_draws_without_mutating_original(dataset_root):
    record = load_assignment(dataset_root).images[0]
    with Image.open(record.path) as image:
        image.load()
        before = image.tobytes()
        rendered = draw_numbered_boxes(image, record.parse_result.annotations, 0)

        assert image.tobytes() == before
        assert rendered.tobytes() != before


def test_reference_placeholder_is_stable_size(dataset_root):
    class_info = load_assignment(dataset_root).classes[4]

    placeholder = reference_placeholder(class_info)

    assert placeholder.size == (240, 180)


@pytest.mark.parametrize("yaml_names", [[f"Product {i:02d}" for i in range(89)], {i: f"Product {i:02d}" for i in range(89)}])
def test_loads_yaml_list_and_dictionary_class_formats(dataset_root, yaml_names):
    (dataset_root / "classes.txt").unlink()
    (dataset_root / "data.yaml").write_text(yaml.safe_dump({"names": yaml_names}), encoding="utf-8")

    dataset = load_assignment(dataset_root)

    assert dataset.classes[88].name == "Product 88"


def test_rejects_class_mapping_that_is_not_exactly_zero_through_88(dataset_root):
    (dataset_root / "classes.txt").write_text("Only one\n", encoding="utf-8")

    with pytest.raises(DatasetLoadError, match="exactly 89"):
        load_assignment(dataset_root)


def test_nested_images_map_to_nested_label_paths(dataset_root):
    nested_image = dataset_root / "images" / "aisle" / "b.png"
    nested_image.parent.mkdir()
    Image.new("RGB", (20, 20), "black").save(nested_image)
    nested_label = dataset_root / "labels" / "aisle" / "b.txt"
    nested_label.parent.mkdir()
    nested_label.write_text("2 0.5 0.5 0.5 0.5\n", encoding="utf-8")

    dataset = load_assignment(dataset_root)

    assert dataset.images[1].relative_path == "images/aisle/b.png"
    assert dataset.images[1].label_path == nested_label


def test_missing_empty_malformed_and_corrupt_items_become_problems(dataset_root):
    Image.new("RGB", (20, 20), "white").save(dataset_root / "images" / "missing.jpg")
    Image.new("RGB", (20, 20), "white").save(dataset_root / "images" / "empty.jpg")
    (dataset_root / "labels" / "empty.txt").write_text("", encoding="utf-8")
    Image.new("RGB", (20, 20), "white").save(dataset_root / "images" / "bad.jpg")
    (dataset_root / "labels" / "bad.txt").write_text("broken label\n", encoding="utf-8")
    (dataset_root / "images" / "corrupt.jpg").write_bytes(b"not an image")

    dataset = load_assignment(dataset_root)

    messages = [problem.message for problem in dataset.problems]
    assert any("missing label" in message for message in messages)
    assert any("malformed annotation" in message for message in messages)
    assert any("could not open image" in message for message in messages)
    empty = next(record for record in dataset.images if record.path.name == "empty.jpg")
    assert empty.parse_result.annotations == ()
