import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def unique_name(prefix="pytest-resource"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def resource_payload(name):
    return {
        "name": name,
        "resource_type": "docker",
        "desired_state": {
            "image": "nginx:alpine",
            "replicas": 1,
        },
        "dependencies": [],
    }


def test_create_resource():
    name = unique_name()

    response = client.post(
        "/resources",
        json=resource_payload(name),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == name
    assert data["resource_type"] == "docker"
    assert data["version"] == 1
    assert data["status"] == "PENDING"


def test_duplicate_resource_name_is_rejected():
    name = unique_name()

    first = client.post(
        "/resources",
        json=resource_payload(name),
    )

    assert first.status_code == 201

    second = client.post(
        "/resources",
        json=resource_payload(name),
    )

    assert second.status_code == 409


def test_idempotent_create_returns_same_resource():
    name = unique_name("idempotent")
    key = f"pytest-{uuid.uuid4()}"

    first = client.post(
        "/resources",
        json=resource_payload(name),
        headers={
            "Idempotency-Key": key,
        },
    )

    assert first.status_code == 201

    first_data = first.json()

    second = client.post(
        "/resources",
        json=resource_payload(name),
        headers={
            "Idempotency-Key": key,
        },
    )

    assert second.status_code == 201

    second_data = second.json()

    assert second_data["id"] == first_data["id"]
    assert second_data["name"] == first_data["name"]


def test_idempotency_key_reused_with_different_request_is_rejected():
    name1 = unique_name("idempotency")
    name2 = unique_name("idempotency")
    key = f"pytest-conflict-{uuid.uuid4()}"

    first = client.post(
        "/resources",
        json=resource_payload(name1),
        headers={
            "Idempotency-Key": key,
        },
    )

    assert first.status_code == 201

    second_payload = resource_payload(name2)

    second = client.post(
        "/resources",
        json=second_payload,
        headers={
            "Idempotency-Key": key,
        },
    )

    assert second.status_code == 409

    assert (
        "Idempotency key was already used"
        in second.json()["detail"]
    )


def test_optimistic_concurrency_control():
    name = unique_name("concurrency")

    create_response = client.post(
        "/resources",
        json=resource_payload(name),
    )

    assert create_response.status_code == 201

    resource = create_response.json()

    resource_id = resource["id"]
    current_version = resource["version"]

    update_payload = {
        "desired_state": {
            "image": "nginx:alpine",
            "replicas": 2,
        },
        "expected_version": current_version,
        "dependencies": [],
    }

    first_update = client.put(
        f"/resources/{resource_id}",
        json=update_payload,
    )

    assert first_update.status_code == 200

    assert first_update.json()["version"] == (
        current_version + 1
    )

    conflicting_update = client.put(
        f"/resources/{resource_id}",
        json=update_payload,
    )

    assert conflicting_update.status_code == 409

    detail = conflicting_update.json()["detail"]

    assert detail["message"] == "Resource version conflict"
    assert detail["expected_version"] == current_version
    assert detail["current_version"] == current_version + 1


def test_concurrent_updates_conflict():
    import uuid

    resource_name = f"concurrent-conflict-{uuid.uuid4().hex[:8]}"

    create_response = client.post(
        "/resources",
        json={
            "name": resource_name,
            "resource_type": "container",
            "desired_state": {
                "image": "nginx:alpine",
                "replicas": 1,
            },
        },
        headers={
            "Idempotency-Key": f"concurrent-{uuid.uuid4()}"
        },
    )

    assert create_response.status_code == 201

    resource = create_response.json()

    resource_id = resource["id"]
    initial_version = resource["version"]

    update_a = client.put(
        f"/resources/{resource_id}",
        json={
            "desired_state": {
                "image": "nginx:alpine",
                "replicas": 2,
            },
            "expected_version": initial_version,
        },
    )

    assert update_a.status_code == 200

    update_b = client.put(
        f"/resources/{resource_id}",
        json={
            "desired_state": {
                "image": "nginx:alpine",
                "replicas": 3,
            },
            "expected_version": initial_version,
        },
    )

    assert update_b.status_code == 409

    detail = update_b.json()["detail"]

    assert detail["message"] == "Resource version conflict"
    assert detail["expected_version"] == initial_version
