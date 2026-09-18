from io import BytesIO
from zipfile import ZipFile

from tests.api.test_annotations import first_annotation
from tests.api.test_catalogs import upload_catalog
from tests.api.test_projects import create_project


def test_export_replaces_only_selected_class_tokens_and_never_mutates_originals(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(api_client, catalog_id).json()
    first = first_annotation(api_client, project["id"], annotation_index=0)
    project_root = api_client.app.state.context.projects.get(project["id"]).dataset_root
    working_label = project_root / "labels/a.txt"
    backup_label = project_root / "backups/labels_original/a.txt"
    working_before = working_label.read_bytes()
    backup_before = backup_label.read_bytes()

    api_client.patch(
        f"/api/v1/annotations/{first['id']}",
        json={"action": "relabel", "target_class_id": 7},
    )
    response = api_client.get(f"/api/v1/projects/{project['id']}/export")

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        corrected = archive.read("labels/a.txt")
    assert corrected == b"7 0.5 0.5 0.2 0.4\n1 0.25 0.25 0.1 0.1\n"
    assert working_label.read_bytes() == working_before
    assert backup_label.read_bytes() == backup_before

