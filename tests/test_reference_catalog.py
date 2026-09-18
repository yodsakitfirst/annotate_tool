from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image
import pytest
import yaml

from annotate_tool.config import ImportLimits
from annotate_tool.reference_catalog import (
    ReferenceCatalogError,
    import_reference_catalog,
    load_reference_catalog,
)
from scripts.create_reference_catalog import main as convert_docx


def png_bytes(color: str = "red") -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 6), color).save(output, format="PNG")
    return output.getvalue()


def make_catalog_zip(tmp_path: Path, names: dict[int, str]) -> Path:
    archive_path = tmp_path / "catalog.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("catalog.yaml", yaml.safe_dump({"names": names}, sort_keys=True))
        for class_id in names:
            archive.writestr(f"references/{class_id}.png", png_bytes())
    return archive_path


def test_imports_sparse_ids_as_only_target_classes(tmp_path):
    classes = import_reference_catalog(
        make_catalog_zip(tmp_path, {1: "Blue", 7: "Green"}),
        tmp_path / "references",
        ImportLimits(),
    )

    assert [(item.class_id, item.name) for item in classes] == [(1, "Blue"), (7, "Green")]
    assert all(item.reference_path.is_file() for item in classes)
    assert load_reference_catalog(tmp_path / "references") == classes


@pytest.mark.parametrize(
    ("names", "members", "message"),
    [
        ({1: "Blue"}, {}, "missing reference image"),
        ({1: "Blue"}, {"references/1.png": b"broken"}, "unreadable reference image"),
        ({1: "Blue"}, {"references/not-an-id.png": png_bytes()}, "numeric"),
        ({1: "Blue"}, {"references/1.png": png_bytes(), "references/1.jpg": png_bytes()}, "multiple"),
    ],
)
def test_invalid_catalog_leaves_no_destination(tmp_path, names, members, message):
    archive_path = tmp_path / "invalid.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("catalog.yaml", yaml.safe_dump({"names": names}))
        for member, content in members.items():
            archive.writestr(member, content)
    destination = tmp_path / "references"

    with pytest.raises(ReferenceCatalogError, match=message):
        import_reference_catalog(archive_path, destination, ImportLimits())

    assert not destination.exists()


def make_docx(tmp_path: Path, count: int) -> Path:
    document_path = tmp_path / "catalog.docx"
    cells = []
    relationships = []
    with ZipFile(document_path, "w") as archive:
        for class_id in range(count):
            relationship_id = f"rId{class_id + 1}"
            cells.append(
                f'<w:tc><w:p><w:r><w:t>Product {class_id}</w:t></w:r>'
                f'<w:r><w:drawing><a:blip r:embed="{relationship_id}"/></w:drawing></w:r>'
                f'</w:p></w:tc>'
            )
            relationships.append(
                f'<Relationship Id="{relationship_id}" '
                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                f'Target="media/image{class_id}.png"/>'
            )
            archive.writestr(f"word/media/image{class_id}.png", png_bytes())
        document_xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<w:body><w:tbl><w:tr>{"".join(cells)}</w:tr></w:tbl></w:body></w:document>'
        )
        rels_xml = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(relationships)}</Relationships>'
        )
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", rels_xml)
    return document_path


def test_docx_converter_maps_table_cells_row_major(tmp_path):
    output = tmp_path / "catalog.zip"

    assert convert_docx([str(make_docx(tmp_path, 89)), str(output)]) == 0

    with ZipFile(output) as archive:
        data = yaml.safe_load(archive.read("catalog.yaml"))
        reference_names = sorted(
            name for name in archive.namelist() if name.startswith("references/")
        )
    assert data["names"] == {class_id: f"Product {class_id}" for class_id in range(89)}
    assert len(reference_names) == 89
    assert "references/0.png" in reference_names
    assert "references/88.png" in reference_names
