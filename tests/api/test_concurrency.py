from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from tests.api.conftest import dataset_bytes
from tests.api.test_catalogs import upload_catalog
from tests.api.test_projects import create_project


def test_twenty_clients_update_different_annotations_without_lock_errors(api_client):
    label_text = "".join(f"999 0.{(index % 8) + 1} 0.5 0.01 0.01\n" for index in range(20))
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(
        api_client, catalog_id, content=dataset_bytes(label_text=label_text)
    ).json()
    image = api_client.get(f"/api/v1/projects/{project['id']}/images").json()["items"][0]
    annotations = api_client.get(
        f"/api/v1/projects/{project['id']}/images/{image['id']}"
    ).json()["annotations"]

    def save(annotation_id: str):
        started = perf_counter()
        response = api_client.patch(
            f"/api/v1/annotations/{annotation_id}",
            json={"action": "relabel", "target_class_id": 7},
        )
        return response, perf_counter() - started

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(save, [item["id"] for item in annotations]))

    responses = [response for response, _duration in results]
    durations = sorted(duration for _response, duration in results)
    print(f"20-client annotation save p95: {durations[18] * 1000:.1f} ms")
    assert len(responses) == 20
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    assert durations[18] < 0.3, f"p95 save latency was {durations[18]:.3f}s"
    refreshed = api_client.get(
        f"/api/v1/projects/{project['id']}/images/{image['id']}"
    ).json()["annotations"]
    assert all(item["current_class_id"] == 7 for item in refreshed)
