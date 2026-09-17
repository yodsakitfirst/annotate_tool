from pathlib import Path

from PIL import Image
import pytest


def class_names() -> list[str]:
    return [f"Product {class_id:02d}" for class_id in range(89)]


@pytest.fixture
def dataset_root(tmp_path: Path) -> Path:
    root = tmp_path / "assignment"
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir()
    (root / "references").mkdir()

    image = Image.new("RGB", (100, 80), "#335577")
    image.save(root / "images" / "a.jpg")
    (root / "labels" / "a.txt").write_text(
        "3 0.5 0.5 0.2 0.2\n17 0.2 0.25 0.1 0.2\n",
        encoding="utf-8",
    )
    (root / "classes.txt").write_text("\n".join(class_names()) + "\n", encoding="utf-8")
    Image.new("RGB", (60, 40), "#aa3333").save(root / "references" / "3.jpg")
    Image.new("RGB", (60, 40), "#33aa33").save(root / "references" / "17.png")
    return root
