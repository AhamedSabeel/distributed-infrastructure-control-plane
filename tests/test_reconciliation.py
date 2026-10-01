from types import SimpleNamespace
from unittest.mock import MagicMock

from app.reconciler.reconciliation import ReconciliationService


def make_resource(
    status="PENDING",
    desired_state=None,
):
    if desired_state is None:
        desired_state = {
            "image": "nginx:alpine",
            "replicas": 1,
        }

    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        name="test-resource",
        status=status,
        desired_state=desired_state,
        dependencies=[],
        observed_state={},
        last_error=None,
        retry_count=0,
        max_retries=5,
        next_retry_at=None,
        version=1,
    )


def make_service():
    db = MagicMock()

    service = ReconciliationService(db)

    service.infrastructure = MagicMock()

    return service, db


def test_converged_resource_becomes_ready():
    service, db = make_service()

    resource = make_resource(
        status="PENDING"
    )

    service.infrastructure.get_observed_state.return_value = {
        "resource_name": "test-resource",
        "running_replicas": 1,
        "stopped_replicas": 0,
        "total_replicas": 1,
        "containers": ["test-resource-1"],
        "stopped_containers": [],
        "container_details": [
            {
                "name": "test-resource-1",
                "status": "running",
                "image": "nginx:alpine",
            }
        ],
    }

    service.reconcile(resource)

    assert resource.status == "READY"
    assert resource.last_error is None
    assert resource.retry_count == 0

    service.infrastructure.create_resource.assert_not_called()

    db.commit.assert_called()


def test_drift_triggers_reconciliation():
    service, db = make_service()

    resource = make_resource(
        status="READY"
    )

    drifted_state = {
        "resource_name": "test-resource",
        "running_replicas": 0,
        "stopped_replicas": 1,
        "total_replicas": 1,
        "containers": [],
        "stopped_containers": ["test-resource-1"],
        "container_details": [
            {
                "name": "test-resource-1",
                "status": "exited",
                "image": "nginx:alpine",
            }
        ],
    }

    converged_state = {
        "resource_name": "test-resource",
        "running_replicas": 1,
        "stopped_replicas": 0,
        "total_replicas": 1,
        "containers": ["test-resource-1"],
        "stopped_containers": [],
        "container_details": [
            {
                "name": "test-resource-1",
                "status": "running",
                "image": "nginx:alpine",
            }
        ],
    }

    service.infrastructure.get_observed_state.side_effect = [
        drifted_state,
        converged_state,
    ]

    service.reconcile(resource)

    assert resource.status == "READY"

    service.infrastructure.create_resource.assert_called_once_with(
        resource_name="test-resource",
        desired_state=resource.desired_state,
    )

    db.commit.assert_called()


def test_unresolved_drift_becomes_drifted():
    service, db = make_service()

    resource = make_resource(
        status="READY"
    )

    drifted_state = {
        "resource_name": "test-resource",
        "running_replicas": 0,
        "stopped_replicas": 1,
        "total_replicas": 1,
        "containers": [],
        "stopped_containers": ["test-resource-1"],
        "container_details": [
            {
                "name": "test-resource-1",
                "status": "exited",
                "image": "nginx:alpine",
            }
        ],
    }

    service.infrastructure.get_observed_state.return_value = (
        drifted_state
    )

    service.reconcile(resource)

    assert resource.status == "DRIFTED"

    service.infrastructure.create_resource.assert_called_once()

    db.commit.assert_called()


def test_missing_dependency_blocks_resource():
    service, db = make_service()

    resource = make_resource(
        status="PENDING"
    )

    resource.dependencies = [
        "database"
    ]

    service.db.query.return_value.filter.return_value.all.return_value = []

    service.reconcile(resource)

    assert resource.status == "BLOCKED"

    assert (
        resource.last_error
        == "Missing dependencies: database"
    )

    service.infrastructure.get_observed_state.assert_not_called()

    db.commit.assert_called()


def test_not_ready_dependency_blocks_resource():
    service, db = make_service()

    resource = make_resource(
        status="PENDING"
    )

    resource.dependencies = [
        "database"
    ]

    dependency = SimpleNamespace(
        name="database",
        status="RECONCILING",
    )

    service.db.query.return_value.filter.return_value.all.return_value = [
        dependency
    ]

    service.reconcile(resource)

    assert resource.status == "BLOCKED"

    assert (
        resource.last_error
        == "Dependencies not ready: database"
    )

    service.infrastructure.get_observed_state.assert_not_called()
