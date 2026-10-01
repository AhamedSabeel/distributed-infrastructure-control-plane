from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.reconciler.reconciliation import ReconciliationService


def make_resource(
    status="READY",
    retry_count=0,
    max_retries=3,
):
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        name="retry-test",
        status=status,
        desired_state={
            "image": "nginx:alpine",
            "replicas": 1,
        },
        observed_state={},
        dependencies=[],
        version=1,
        retry_count=retry_count,
        max_retries=max_retries,
        next_retry_at=None,
        last_error=None,
    )


def make_service(resource):
    db = MagicMock()
    infrastructure = MagicMock()

    db.query.return_value.filter.return_value.all.return_value = []

    service = ReconciliationService(db=db)
    service.infrastructure = infrastructure

    return service, db, infrastructure


def test_infrastructure_failure_increments_retry_count():
    resource = make_resource()
    service, db, infrastructure = make_service(resource)

    infrastructure.get_observed_state.side_effect = Exception(
        "Docker unavailable"
    )

    service.reconcile(resource)

    assert resource.retry_count == 1
    assert resource.last_error == "Docker unavailable"
    assert resource.status == "RECONCILING"
    assert resource.next_retry_at is not None


def test_retry_uses_exponential_backoff():
    resource = make_resource(retry_count=1)
    service, db, infrastructure = make_service(resource)

    infrastructure.get_observed_state.side_effect = Exception(
        "Docker unavailable"
    )

    before = datetime.now(timezone.utc)

    service.reconcile(resource)

    after = datetime.now(timezone.utc)

    assert resource.retry_count == 2
    assert resource.next_retry_at is not None

    expected_min = before + timedelta(seconds=4)
    expected_max = after + timedelta(seconds=4)

    assert resource.next_retry_at >= expected_min
    assert resource.next_retry_at <= expected_max


def test_resource_fails_after_max_retries():
    resource = make_resource(
        status="RECONCILING",
        retry_count=2,
        max_retries=3,
    )

    service, db, infrastructure = make_service(resource)

    infrastructure.get_observed_state.side_effect = Exception(
        "Infrastructure permanently unavailable"
    )

    service.reconcile(resource)

    assert resource.retry_count == 3
    assert resource.status == "FAILED"
    assert resource.last_error == "Infrastructure permanently unavailable"


def test_successful_reconciliation_clears_retry_state():
    resource = make_resource(
        status="RECONCILING",
        retry_count=2,
    )

    service, db, infrastructure = make_service(resource)

    infrastructure.get_observed_state.return_value = {
        "running_replicas": 1,
        "stopped_replicas": 0,
        "total_replicas": 1,
        "containers": [],
    }

    service.reconcile(resource)

    assert resource.status == "READY"
    assert resource.retry_count == 0
    assert resource.last_error is None
    assert resource.next_retry_at is None
