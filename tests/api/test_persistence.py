from fastapi.testclient import TestClient

from annotate_tool.api.dependencies import Settings
from annotate_tool.api.main import create_app
from tests.api.test_annotations import first_annotation
from tests.api.test_catalogs import upload_catalog
from tests.api.test_projects import create_project


def test_restart_with_same_data_directory_preserves_catalog_project_and_decision(tmp_path):
    settings = Settings(data_dir=tmp_path / "persistent", frontend_dist=tmp_path / "frontend")
    with TestClient(create_app(settings)) as first_client:
        catalog = upload_catalog(first_client).json()
        project = create_project(first_client, catalog["id"]).json()
        annotation = first_annotation(first_client, project["id"], annotation_index=1)
        saved = first_client.patch(
            f"/api/v1/annotations/{annotation['id']}",
            json={"action": "relabel", "target_class_id": 7},
        )
        assert saved.status_code == 200

    with TestClient(create_app(settings)) as restarted_client:
        assert restarted_client.get("/api/v1/catalogs").json()["items"][0]["id"] == catalog["id"]
        assert restarted_client.get("/api/v1/projects").json()["items"][0]["id"] == project["id"]
        restored = first_annotation(restarted_client, project["id"], annotation_index=1)

    assert restored["current_class_id"] == 7
    assert restored["decision"] == "relabel"
    assert restored["version"] == 1
