from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont


def _save_scene(path: Path, boxes: list[tuple[int, int, int, int, str]]) -> None:
    image = Image.new("RGB", (960, 640), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    for left, top, right, bottom, color in boxes:
        draw.rectangle((left, top, right, bottom), fill=color, outline="#0F172A", width=4)
    image.save(path, quality=92)


def _save_reference(path: Path, class_id: int) -> None:
    hue = (class_id * 47) % 255
    image = Image.new("RGB", (240, 180), (50 + hue // 3, 80 + hue // 4, 110 + hue // 5))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    draw.rounded_rectangle((25, 25, 215, 155), radius=18, fill="#F8FAFC", outline="#0F172A", width=3)
    draw.multiline_text(
        (50, 62),
        f"Product {class_id:02d}\nClass ID {class_id}",
        fill="#0F172A",
        font=font,
        spacing=10,
        align="center",
    )
    image.save(path, quality=90)


def create_sample_archive(output_path: Path) -> Path:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="annotation_sample_") as temporary:
        root = Path(temporary)
        images = root / "images"
        labels = root / "labels"
        references = root / "references"
        images.mkdir()
        labels.mkdir()
        references.mkdir()

        _save_scene(
            images / "multiple_boxes.jpg",
            [
                (105, 145, 345, 505, "#DC2626"),
                (535, 180, 805, 480, "#2563EB"),
            ],
        )
        (labels / "multiple_boxes.txt").write_text(
            "3 0.234375 0.5078125 0.25 0.5625\n"
            "17 0.6979167 0.515625 0.28125 0.46875\n",
            encoding="utf-8",
        )

        _save_scene(images / "empty.jpg", [],)
        (labels / "empty.txt").write_text("", encoding="utf-8")

        _save_scene(images / "missing_label.jpg", [(300, 180, 640, 470, "#16A34A")])

        _save_scene(images / "malformed.jpg", [(240, 120, 700, 520, "#9333EA")])
        (labels / "malformed.txt").write_text("not a valid YOLO annotation\n", encoding="utf-8")

        (root / "classes.txt").write_text(
            "\n".join(f"Product {class_id:02d}" for class_id in range(89)) + "\n",
            encoding="utf-8",
        )
        for class_id in range(89):
            _save_reference(references / f"{class_id}.jpg", class_id)

        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    return output_path


if __name__ == "__main__":
    generated = create_sample_archive(Path("sample_data/sample_assignment.zip"))
    print(generated)
