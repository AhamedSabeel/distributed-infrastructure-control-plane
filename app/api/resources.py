import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
)
from app.database.database import get_db
from app.events.event_service import EventService
from app.infrastructure.docker_adapter import DockerAdapter
from app.models.idempotency_record import IdempotencyRecord
from app.models.resource import Resource


router = APIRouter(
    prefix="/resources",
    tags=["Resources"],
)


# ---------------------------------------------------------
# CREATE RESOURCE
# ---------------------------------------------------------

@router.post(
    "",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_resource(
    resource_data: ResourceCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    request_payload = resource_data.model_dump(
        mode="json"
    )

    request_hash = hashlib.sha256(
        json.dumps(
            request_payload,
            sort_keys=True,
        ).encode()
    ).hexdigest()

    # -----------------------------------------------------
    # IDEMPOTENCY CHECK
    # -----------------------------------------------------

    if idempotency_key:

        existing_request = (
            db.query(IdempotencyRecord)
            .filter(
                IdempotencyRecord.idempotency_key
                == idempotency_key
            )
            .first()
        )

        if existing_request:

            if (
                existing_request.request_hash
                != request_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Idempotency key was already used "
                        "with a different request"
                    ),
                )

            resource = (
                db.query(Resource)
                .filter(
                    Resource.id
                    == existing_request.resource_id
                )
                .first()
            )

            if not resource:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Idempotency record exists but "
                        "the associated resource no longer exists"
                    ),
                )

            return resource

    # -----------------------------------------------------
    # RESOURCE EXISTENCE CHECK
    # -----------------------------------------------------

    existing_resource = (
        db.query(Resource)
        .filter(
            Resource.name == resource_data.name
        )
        .first()
    )

    if existing_resource:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource with this name already exists",
        )

    # -----------------------------------------------------
    # CREATE RESOURCE
    # -----------------------------------------------------

    resource = Resource(
        name=resource_data.name,
        resource_type=resource_data.resource_type,
        desired_state=resource_data.desired_state,
        dependencies=resource_data.dependencies,
        observed_state={},
        status="PENDING",
        version=1,
    )

    db.add(resource)
    db.flush()

    # -----------------------------------------------------
    # STORE IDEMPOTENCY RECORD
    # -----------------------------------------------------

    if idempotency_key:

        idempotency_record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            resource_id=resource.id,
        )

        db.add(idempotency_record)

    db.commit()
    db.refresh(resource)

    # -----------------------------------------------------
    # PUBLISH EVENT
    # -----------------------------------------------------

    EventService().publish(
        event_type="ResourceCreated",
        resource_id=resource.id,
    )

    return resource



# ---------------------------------------------------------
# LIST RESOURCES
# ---------------------------------------------------------

@router.get(
    "",
    response_model=list[ResourceResponse],
)
def list_resources(
    db: Session = Depends(get_db),
):
    return (
        db.query(Resource)
        .order_by(Resource.created_at.desc())
        .all()
    )













@router.get(
    "/{resource_id}/history",
)
def get_resource_history(
    resource_id: UUID,
    db: Session = Depends(get_db),
):
    resource = (
        db.query(Resource)
        .filter(Resource.id == str(resource_id))
        .first()
    )

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    from app.models.state_history import StateHistory

    history = (
        db.query(StateHistory)
        .filter(
            StateHistory.resource_id == resource.id
        )
        .order_by(
            StateHistory.created_at.desc()
        )
        .all()
    )

    return history



















# ---------------------------------------------------------
# GET RESOURCE
# ---------------------------------------------------------

@router.get(
    "/{resource_id}",
    response_model=ResourceResponse,
)
def get_resource(
    resource_id: UUID,
    db: Session = Depends(get_db),
):
    resource = (
        db.query(Resource)
        .filter(Resource.id == str(resource_id))
        .first()
    )

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    return resource


# ---------------------------------------------------------
# UPDATE RESOURCE
# ---------------------------------------------------------

@router.put(
    "/{resource_id}",
    response_model=ResourceResponse,
)
def update_resource(
    resource_id: UUID,
    resource_data: ResourceUpdate,
    db: Session = Depends(get_db),
):
    resource = (
        db.query(Resource)
        .filter(Resource.id == str(resource_id))
        .first()
    )

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    # Optimistic concurrency control
    if (
        resource_data.expected_version is not None
        and resource_data.expected_version != resource.version
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Resource version conflict",
                "expected_version": resource_data.expected_version,
                "current_version": resource.version,
            },
        )

    resource.desired_state = resource_data.desired_state
    resource.dependencies = resource_data.dependencies
    resource.version += 1
    resource.status = "PENDING"
    resource.last_error = None
    resource.retry_count = 0
    resource.next_retry_at = None

    db.commit()
    db.refresh(resource)

    EventService().publish(
        event_type="ResourceUpdated",
        resource_id=resource.id,
    )

    return resource


# ---------------------------------------------------------
# DELETE RESOURCE
# ---------------------------------------------------------

@router.delete(
    "/{resource_id}",
    response_model=ResourceResponse,
)
def delete_resource(
    resource_id: UUID,
    db: Session = Depends(get_db),
):
    resource = (
        db.query(Resource)
        .filter(Resource.id == str(resource_id))
        .first()
    )

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    resource.status = "DELETING"
    resource.version += 1

    db.commit()
    db.refresh(resource)

    EventService().publish(
        event_type="ResourceDeleted",
        resource_id=resource.id,
    )

    return resource

# ---------------------------------------------------------
# MANUAL SYNCHRONIZATION
# ---------------------------------------------------------

@router.post(
    "/{resource_id}/sync",
    response_model=ResourceResponse,
)
def sync_resource(
    resource_id: UUID,
    db: Session = Depends(get_db),
):
    resource = (
        db.query(Resource)
        .filter(Resource.id == str(resource_id))
        .first()
    )

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    adapter = DockerAdapter()

    try:
        adapter.create_resource(
            resource_name=resource.name,
            desired_state=resource.desired_state,
        )

        observed_state = adapter.get_observed_state(
            resource_name=resource.name,
            desired_state=resource.desired_state,
        )

        resource.observed_state = observed_state

        desired_replicas = int(
            resource.desired_state.get("replicas", 1)
        )

        actual_replicas = int(
            observed_state.get("running_replicas", 0)
        )

        if desired_replicas == actual_replicas:
            resource.status = "READY"
            resource.last_error = None
        else:
            resource.status = "DRIFTED"

        db.commit()
        db.refresh(resource)

        return resource

    except Exception as error:
        resource.status = "FAILED"
        resource.last_error = str(error)

        db.commit()
        db.refresh(resource)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Infrastructure synchronization failed",
        )
