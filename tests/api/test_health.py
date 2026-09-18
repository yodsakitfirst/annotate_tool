def test_health_reports_database_and_writable_storage_without_paths(api_client):
    response = api_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "available",
        "storage": "writable",
    }
    assert str(api_client.app.state.context.paths.root) not in response.text


def test_unknown_api_route_uses_structured_error(api_client):
    response = api_client.get("/api/v1/not-a-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Resource not found", "details": {}}
    }


def test_unhandled_errors_are_translated_without_tracebacks(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from annotate_tool.api.dependencies import Settings
    from annotate_tool.api.main import create_app

    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "frontend"))

    def explode(*_args, **_kwargs):
        raise RuntimeError("secret server detail")
    monkeypatch.setattr(app.state.context.projects, "list", explode)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error", "details": {}}
    }
    assert "secret server detail" not in response.text
