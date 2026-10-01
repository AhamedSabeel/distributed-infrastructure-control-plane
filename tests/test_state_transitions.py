from types import SimpleNamespace

import pytest

from app.services.state_transition_service import (
    validate_transition,
)


def resource_with_status(status: str):
    return SimpleNamespace(
        status=status,
        name="test-resource",
    )


@pytest.mark.parametrize(
    "current_status,new_status",
    [
        ("PENDING", "RECONCILING"),
        ("PENDING", "BLOCKED"),
        ("PENDING", "READY"),
        ("RECONCILING", "READY"),
        ("RECONCILING", "DRIFTED"),
        ("RECONCILING", "FAILED"),
        ("READY", "PENDING"),
        ("READY", "RECONCILING"),
        ("READY", "DRIFTED"),
        ("READY", "DELETING"),
        ("DRIFTED", "RECONCILING"),
        ("DRIFTED", "READY"),
        ("BLOCKED", "PENDING"),
        ("BLOCKED", "RECONCILING"),
        ("FAILED", "PENDING"),
        ("FAILED", "DELETING"),
        ("DELETING", "DELETED"),
    ],
)
def test_valid_state_transitions(
    current_status,
    new_status,
):
    resource = resource_with_status(current_status)

    validate_transition(
        resource,
        new_status,
    )


@pytest.mark.parametrize(
    "current_status,new_status",
    [
        ("DELETED", "READY"),
        ("DELETED", "PENDING"),
        ("DELETED", "RECONCILING"),
        ("FAILED", "READY"),
        ("FAILED", "RECONCILING"),
        ("DELETING", "READY"),
        ("READY", "DELETED"),
        ("BLOCKED", "READY"),
    ],
)
def test_invalid_state_transitions(
    current_status,
    new_status,
):
    resource = resource_with_status(current_status)

    with pytest.raises(ValueError):
        validate_transition(
            resource,
            new_status,
        )


@pytest.mark.parametrize(
    "status",
    [
        "PENDING",
        "RECONCILING",
        "READY",
        "DRIFTED",
        "BLOCKED",
        "FAILED",
        "DELETING",
        "DELETED",
    ],
)
def test_same_state_transition_is_allowed(status):
    resource = resource_with_status(status)

    validate_transition(
        resource,
        status,
    )
