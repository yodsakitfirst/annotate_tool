from tests.api.conftest import catalog_bytes


def upload_catalog(api_client, name="Shared targets", content=None):
    return api_client.post(
        "/api/v1/catalogs",
        data={"name": name},
        files={"catalog_zip": ("catalog.zip", content or catalog_bytes(), "application/zip")},
    )


def test_empty_catalog_list_and_sparse_upload(api_client):
    assert api_client.get("/api/v1/catalogs").json() == {
        "items": [], "limit": 50, "offset": 0
    }

    created = upload_catalog(api_client)

    assert created.status_code == 201
    catalog = created.json()
    assert catalog["name"] == "Shared targets"
    assert catalog["class_count"] == 2
    detail = api_client.get(f"/api/v1/catalogs/{catalog['id']}").json()
    assert detail["id"] == catalog["id"]
    classes = api_client.get(f"/api/v1/catalogs/{catalog['id']}/classes?query=mega").json()
    assert [(item["class_id"], item["name"]) for item in classes["items"]] == [(7, "Omega")]
    assert classes["items"][0]["thumbnail_url"].endswith("/classes/7")


def test_invalid_catalog_rolls_back_and_returns_structured_error(api_client):
    response = upload_catalog(api_client, content=b"not a zip")

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "catalog_invalid"
    assert "ZIP" in body["message"]
    assert api_client.get("/api/v1/catalogs").json()["items"] == []
    assert list(api_client.app.state.context.paths.staging.iterdir()) == []
    assert list(api_client.app.state.context.paths.catalogs.iterdir()) == []


def test_catalog_search_and_pagination(api_client):
    upload_catalog(api_client, name="First")
    upload_catalog(api_client, name="Second")

    result = api_client.get("/api/v1/catalogs?query=second&limit=1&offset=0").json()

    assert [item["name"] for item in result["items"]] == ["Second"]
    assert result["limit"] == 1

