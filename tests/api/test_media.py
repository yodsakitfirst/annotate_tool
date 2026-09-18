from pathlib import Path

from tests.api.test_catalogs import upload_catalog


def test_catalog_media_is_served_with_cache_headers(api_client):
    catalog = upload_catalog(api_client).json()
    media_url = api_client.get(
        f"/api/v1/catalogs/{catalog['id']}/classes?query=7"
    ).json()["items"][0]["thumbnail_url"]

    response = api_client.get(media_url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "public" in response.headers["cache-control"]
    assert response.headers["etag"]


def test_media_rejects_database_path_outside_data_root(api_client, tmp_path: Path):
    catalog = upload_catalog(api_client).json()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    database = api_client.app.state.context.database
    with database.transaction() as connection:
        connection.execute(
            "UPDATE catalog_classes SET reference_path = ? WHERE catalog_id = ? AND class_id = 1",
            (str(outside.resolve()), catalog["id"]),
        )

    response = api_client.get(f"/media/catalogs/{catalog['id']}/classes/1")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "media_not_found"
    assert str(outside) not in response.text
