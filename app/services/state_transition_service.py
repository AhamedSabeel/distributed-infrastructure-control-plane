from app.models.resource import Resource


ALLOWED_TRANSITIONS = {
    "PENDING": {
        "RECONCILING",
        "BLOCKED",
        "DELETING",
        "FAILED",
        "READY",
        "DRIFTED",
    },
    "RECONCILING": {
        "READY",
        "DRIFTED",
        "FAILED",
        "BLOCKED",
        "DELETING",
    },
    "READY": {
        "PENDING",
        "RECONCILING",
        "DRIFTED",
        "DELETING",
        "FAILED",
    },
    "DRIFTED": {
        "RECONCILING",
        "READY",
        "FAILED",
        "DELETING",
    },
    "BLOCKED": {
        "PENDING",
        "RECONCILING",
        "FAILED",
        "DELETING",
    },
    "FAILED": {
        "PENDING",
        "DELETING",
    },
    "DELETING": {
        "DELETED",
        "FAILED",
    },
    "DELETED": set(),
}


def validate_transition(
    resource: Resource,
    new_status: str,
) -> None:
    current_status = resource.status

    if current_status == new_status:
        return

    allowed_states = ALLOWED_TRANSITIONS.get(
        current_status,
        set(),
    )

    if new_status not in allowed_states:
        raise ValueError(
            f"Invalid state transition: "
            f"{current_status} -> {new_status}"
        )
