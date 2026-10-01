from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.models.state_history import StateHistory


def record_history(
    db: Session,
    resource: Resource,
    event_type: str,
    message: str | None = None,
):
    history = StateHistory(
        resource_id=resource.id,
        resource_name=resource.name,
        event_type=event_type,
        status=resource.status,
        version=resource.version,
        desired_state=resource.desired_state or {},
        observed_state=resource.observed_state or {},
        message=message,
    )

    db.add(history)
