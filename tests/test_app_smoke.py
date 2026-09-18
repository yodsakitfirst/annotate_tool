from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

from annotate_tool.config import AppPaths
from annotate_tool.models import ClassInfo
from annotate_tool.progress import ProgressRepository


APP_PATH = Path(__file__).parents[1] / "app.py"


def seed_assignment(runtime: Path, needs_review: bool = False) -> None:
    paths = AppPaths.from_root(runtime)
    paths.ensure()
    root = paths.assignments / "dataset-1"
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir()
    (root / "references").mkdir()
    Image.new("RGB", (120, 80), "#224466").save(root / "images" / "a.jpg")
    source_class_id = 89 if needs_review else 3
    (root / "labels" / "a.txt").write_text(
        f"{source_class_id} 0.5 0.5 0.25 0.5\n",
        encoding="utf-8",
    )
    class_names = [f"Product {class_id:02d}" for class_id in range(89)]
    if needs_review:
        class_names.append("Needs Review")
    (root / "classes.txt").write_text(
        "\n".join(class_names) + "\n",
        encoding="utf-8",
    )
    Image.new("RGB", (50, 50), "#aa3333").save(root / "references" / "3.jpg")
    repository = ProgressRepository(paths.database)
    repository.initialize()
    repository.register_project("dataset-1", "Sample dataset", root, root / "references", "Alice")
    repository.replace_reference_classes(
        "dataset-1",
        (ClassInfo(3, "Product 03", root / "references" / "3.jpg"),),
    )


def open_seeded_app(monkeypatch, runtime: Path) -> AppTest:
    monkeypatch.setenv("ANNOTATE_TOOL_DATA_DIR", str(runtime))
    app = AppTest.from_file(APP_PATH).run(timeout=15)
    app.text_input(key="annotator_name").set_value("Alice").run(timeout=15)
    return app


def test_app_starts_and_shows_import_state(monkeypatch, tmp_path):
    monkeypatch.setenv("ANNOTATE_TOOL_DATA_DIR", str(tmp_path / "runtime"))

    app = AppTest.from_file(APP_PATH).run(timeout=15)

    assert not app.exception
    assert app.title[0].value == "YOLO Class Review"
    assert any("Import a project" in item.value for item in app.info)


def test_seeded_assignment_renders_review_controls(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    seed_assignment(runtime)
    app = open_seeded_app(monkeypatch, runtime)

    assert not app.exception
    assert app.selectbox[0].value == "Sample dataset · Alice"
    assert any(button.label == "✅ Correct" for button in app.button)
    assert any(button.label == "Skip" for button in app.button)
    assert app.text_input(key="class_query").label == "Search classes"
    assert any(metric.label == "Reviewed" and metric.value == "0 / 1" for metric in app.metric)
    assert not any(button.label.startswith("Object ") for button in app.button)


def test_correct_button_records_progress_and_shows_completion(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    seed_assignment(runtime)
    app = open_seeded_app(monkeypatch, runtime)

    correct = next(button for button in app.button if button.label == "✅ Correct")
    correct.click().run(timeout=15)

    assert not app.exception
    assert any("Assignment complete" in item.value for item in app.success)
    reopened = ProgressRepository(AppPaths.from_root(runtime).database)
    reopened.initialize()
    assert reopened.summary("dataset-1")["correct"] == 1


def test_needs_review_must_be_relabelled_to_a_product_class(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    seed_assignment(runtime, needs_review=True)
    app = open_seeded_app(monkeypatch, runtime)

    assert not app.exception
    correct = next(button for button in app.button if button.label == "✅ Correct")
    assert correct.disabled

    app.text_input(key="class_query").set_value("89").run(timeout=15)

    assert not app.exception
    assert any("No classes match" in item.value for item in app.info)
