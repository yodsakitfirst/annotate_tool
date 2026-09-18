from tests.api.conftest import dataset_bytes
from tests.api.test_catalogs import upload_catalog


def create_project(api_client, catalog_id: str, name="Dataset A", content=None):
    return api_client.post(
        "/api/v1/projects",
        data={"name": name, "catalog_id": catalog_id},
        files={"dataset_zip": ("dataset.zip", content or dataset_bytes(), "application/zip")},
    )


def test_project_import_uses_reusable_catalog_and_database_summaries(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]

    first = create_project(api_client, catalog_id, "First")
    second = create_project(api_client, catalog_id, "Second")

    assert first.status_code == 201
    assert second.status_code == 201
    items = api_client.get("/api/v1/projects").json()["items"]
    assert {item["name"] for item in items} == {"First", "Second"}
    assert all(item["catalog_id"] == catalog_id for item in items)
    assert all(item["image_count"] == 2 for item in items)
    assert all(item["annotation_count"] == 2 for item in items)
    assert all(item["reviewed_count"] == 0 for item in items)
    assert all(item["thumbnail_url"].startswith("/media/images/") for item in items)


def test_project_import_accepts_missing_source_metadata(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]

    response = create_project(
        api_client,
        catalog_id,
        content=dataset_bytes(classes_text=None),
    )

    assert response.status_code == 201


def test_project_import_failure_is_invisible_and_retryable(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]

    failed = create_project(api_client, catalog_id, content=b"bad zip")
    retried = create_project(api_client, catalog_id)

    assert failed.status_code == 422
    assert failed.json()["error"]["code"] == "project_invalid"
    assert retried.status_code == 201
    assert [item["name"] for item in api_client.get("/api/v1/projects").json()["items"]] == ["Dataset A"]
    assert list(api_client.app.state.context.paths.staging.iterdir()) == []


def test_project_import_rejects_unknown_catalog(api_client):
    response = create_project(api_client, "missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "catalog_not_found"

