from typing import Any

from pydantic import BaseModel, Field


class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    resource_type: str = Field(min_length=1, max_length=100)
    desired_state: dict[str, Any]
    dependencies: list[str] = []

class ResourceUpdate(BaseModel):
    desired_state: dict[str, Any]
    expected_version: int | None = None
    dependencies: list[str] = []


class ResourceResponse(BaseModel):
    id: str
    name: str
    resource_type: str
    desired_state: dict[str, Any]
    observed_state: dict[str, Any]
    status: str
    version: int
    last_error: str | None
    dependencies: list[str]

    model_config = {
        "from_attributes": True
    }
