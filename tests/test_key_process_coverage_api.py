from conftest import API


def test_key_process_coverage_endpoint_returns_matrix(client):
    response = client.get(f"{API}/process-map/key-process-coverage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"summary", "activities", "boundary_reviews", "labels"} <= body.keys()


def test_key_process_coverage_endpoint_is_read_only_for_viewer(viewer_client):
    response = viewer_client.get(f"{API}/process-map/key-process-coverage")
    assert response.status_code == 200, response.text
    assert response.request.method == "GET"
