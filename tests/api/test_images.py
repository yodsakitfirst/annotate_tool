from tests.api.test_catalogs import upload_catalog
from tests.api.test_projects import create_project


def test_image_payload_orders_annotations_and_exposes_geometry_and_unknown_source(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(api_client, catalog_id).json()
    images = api_client.get(f"/api/v1/projects/{project['id']}/images").json()["items"]

    assert [item["relative_path"] for item in images] == ["images/a.png", "images/b.png"]
    detail = api_client.get(
        f"/api/v1/projects/{project['id']}/images/{images[0]['id']}"
    ).json()

    assert (detail["width"], detail["height"]) == (20, 12)
    assert detail["media_url"] == f"/media/images/{images[0]['id']}"
    assert [item["line_index"] for item in detail["annotations"]] == [0, 1]
    assert detail["annotations"][0]["source_class_id"] == 999
    assert detail["annotations"][0]["source_class_name"] == "Unknown source class 999"
    assert detail["annotations"][0]["coordinates"] == {
        "x_center": 0.5, "y_center": 0.5, "width": 0.2, "height": 0.4
    }


def test_image_relationship_is_validated(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]
    first = create_project(api_client, catalog_id, "First").json()
    second = create_project(api_client, catalog_id, "Second").json()
    image_id = api_client.get(f"/api/v1/projects/{first['id']}/images").json()["items"][0]["id"]

    response = api_client.get(f"/api/v1/projects/{second['id']}/images/{image_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "image_not_found"


def test_image_media_is_confined_and_available(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(api_client, catalog_id).json()
    image_id = api_client.get(f"/api/v1/projects/{project['id']}/images").json()["items"][0]["id"]

    response = api_client.get(f"/media/images/{image_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
