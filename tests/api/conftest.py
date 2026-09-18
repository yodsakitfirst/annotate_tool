from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient
from PIL import Image
import pytest
import yaml

from annotate_tool.api.main import create_app
from annotate_tool.api.dependencies import Settings


def image_bytes(color: str = "red") -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 12), color).save(output, format="PNG")
    return output.getvalue()


def catalog_bytes(names: dict[int, str] | None = None) -> bytes:
    names = names or {1: "Alpha", 7: "Omega"}
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("catalog.yaml", yaml.safe_dump({"names": names}, allow_unicode=True))
        for class_id in names:
            archive.writestr(f"references/{class_id}.png", image_bytes())
    return output.getvalue()


def dataset_bytes(
    *,
    label_text: str = "999 0.5 0.5 0.2 0.4\n1 0.25 0.25 0.1 0.1\n",
    classes_text: str | None = "one\n",
) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("images/a.png", image_bytes("blue"))
        archive.writestr("images/b.png", image_bytes("green"))
        archive.writestr("labels/a.txt", label_text)
        archive.writestr("labels/b.txt", "")
        if classes_text is not None:
            archive.writestr("classes.txt", classes_text)
    return output.getvalue()


@pytest.fixture
def api_client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "frontend")
    with TestClient(create_app(settings)) as client:
        yield client
