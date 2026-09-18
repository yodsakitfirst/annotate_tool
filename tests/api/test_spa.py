from pathlib import Path

from fastapi.testclient import TestClient

from annotate_tool.api.dependencies import Settings
from annotate_tool.api.main import create_app


def test_fastapi_serves_spa_routes_and_fingerprinted_assets(tmp_path: Path):
    frontend = tmp_path / "dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "index.html").write_text("<main>React application</main>", encoding="utf-8")
    (assets / "app-abc123.js").write_text("console.log('ok')", encoding="utf-8")

    with TestClient(create_app(Settings(data_dir=tmp_path / "data", frontend_dist=frontend))) as client:
        page = client.get("/projects/example/annotate")
        asset = client.get("/assets/app-abc123.js")
        api_missing = client.get("/api/v1/does-not-exist")

    assert page.status_code == 200
    assert "React application" in page.text
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    assert api_missing.status_code == 404
    assert api_missing.json()["error"]["code"] == "not_found"


def test_missing_frontend_returns_controlled_service_error(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "missing"))) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "frontend_unavailable"
