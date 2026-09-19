from pathlib import Path

import yaml


def test_compose_uses_explicit_persistent_host_directory():
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    app = compose["services"]["app"]

    assert "./annotation-data:/data" in app["volumes"]
    assert app["environment"]["ANNOTATE_TOOL_DATA_DIR"] == "/data"
    assert app["restart"] == "unless-stopped"


def test_example_environment_contains_only_supported_runtime_settings():
    lines = {
        line
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }

    assert lines == {"PORT=8000", "ANNOTATE_TOOL_DATA_DIR=/data"}
