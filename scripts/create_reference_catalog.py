from pathlib import Path, PurePosixPath
import posixpath
import sys
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import yaml


NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def convert_docx(source_path: Path, output_path: Path) -> None:
    with ZipFile(source_path) as source:
        document = ElementTree.fromstring(source.read("word/document.xml"))
        relationships_xml = ElementTree.fromstring(source.read("word/_rels/document.xml.rels"))
        relationships = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships_xml.findall("pr:Relationship", NAMESPACES)
        }
        entries: list[tuple[int, str, str, bytes]] = []
        for cell in document.findall(".//w:tc", NAMESPACES):
            blips = cell.findall(".//a:blip", NAMESPACES)
            name = "".join(
                node.text or "" for node in cell.findall(".//w:t", NAMESPACES)
            ).strip()
            if not blips and not name:
                continue
            if len(blips) != 1:
                raise ValueError("each populated DOCX table cell must contain exactly one image")
            if not name:
                raise ValueError("each populated DOCX table cell must contain a class name")
            relationship_id = blips[0].attrib[f"{{{NAMESPACES['r']}}}embed"]
            if relationship_id not in relationships:
                raise ValueError(f"DOCX image relationship is missing: {relationship_id}")
            media_name = posixpath.normpath(
                posixpath.join("word", relationships[relationship_id])
            )
            if not media_name.startswith("word/media/"):
                raise ValueError(f"DOCX image target is unsafe: {media_name}")
            suffix = PurePosixPath(media_name).suffix.casefold()
            entries.append((len(entries), name, suffix, source.read(media_name)))

    if not entries:
        raise ValueError("DOCX contains no populated reference cells")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as output:
        output.writestr(
            "catalog.yaml",
            yaml.safe_dump(
                {"names": {class_id: name for class_id, name, _, _ in entries}},
                sort_keys=True,
                allow_unicode=True,
            ),
        )
        for class_id, _, suffix, content in entries:
            output.writestr(f"references/{class_id}{suffix}", content)


def main(arguments: list[str] | None = None) -> int:
    values = sys.argv[1:] if arguments is None else arguments
    if len(values) != 2:
        raise SystemExit("usage: create_reference_catalog.py INPUT.docx OUTPUT.zip")
    convert_docx(Path(values[0]), Path(values[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
