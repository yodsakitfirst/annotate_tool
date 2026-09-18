from tests.api.test_catalogs import upload_catalog
from tests.api.test_projects import create_project


def first_annotation(api_client, project_id: str, image_index: int = 0, annotation_index: int = 0):
    images = api_client.get(f"/api/v1/projects/{project_id}/images").json()["items"]
    return api_client.get(
        f"/api/v1/projects/{project_id}/images/{images[image_index]['id']}"
    ).json()["annotations"][annotation_index]


def test_correct_relabel_and_skip_return_authoritative_versions(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(api_client, catalog_id).json()
    annotation = first_annotation(api_client, project["id"], annotation_index=1)

    corrected = api_client.patch(
        f"/api/v1/annotations/{annotation['id']}",
        json={"action": "correct", "annotator_name": "Ada"},
    )
    relabelled = api_client.patch(
        f"/api/v1/annotations/{annotation['id']}",
        json={"action": "relabel", "target_class_id": 7, "annotator_name": "Grace"},
    )
    skipped = api_client.patch(
        f"/api/v1/annotations/{annotation['id']}",
        json={"action": "skip", "annotator_name": ""},
    )

    assert corrected.status_code == 200
    assert corrected.json()["version"] == 1
    assert {
        key: relabelled.json()[key]
        for key in ("decision", "current_class_id", "annotator_name", "version")
    } == {"decision": "relabel", "current_class_id": 7, "annotator_name": "Grace", "version": 2}
    assert skipped.json()["decision"] == "skip"
    assert skipped.json()["current_class_id"] == 7
    assert skipped.json()["version"] == 3


def test_target_enforcement_and_failed_save_leave_prior_state(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(api_client, catalog_id).json()
    unknown = first_annotation(api_client, project["id"])

    invalid_correct = api_client.patch(
        f"/api/v1/annotations/{unknown['id']}", json={"action": "correct"}
    )
    invalid_relabel = api_client.patch(
        f"/api/v1/annotations/{unknown['id']}",
        json={"action": "relabel", "target_class_id": 99},
    )
    unchanged = first_annotation(api_client, project["id"])

    assert invalid_correct.status_code == 422
    assert invalid_relabel.status_code == 422
    assert invalid_relabel.json()["error"]["code"] == "target_class_invalid"
    assert unchanged["decision"] is None
    assert unchanged["current_class_id"] == 999
    assert unchanged["version"] == 0


def test_last_write_wins_per_annotation_and_other_box_is_unchanged(api_client):
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(api_client, catalog_id).json()
    first = first_annotation(api_client, project["id"], annotation_index=0)
    second = first_annotation(api_client, project["id"], annotation_index=1)

    api_client.patch(f"/api/v1/annotations/{first['id']}", json={"action": "relabel", "target_class_id": 1})
    latest = api_client.patch(f"/api/v1/annotations/{first['id']}", json={"action": "relabel", "target_class_id": 7})
    second_after = first_annotation(api_client, project["id"], annotation_index=1)

    assert latest.json()["current_class_id"] == 7
    assert latest.json()["version"] == 2
    assert second_after == second
