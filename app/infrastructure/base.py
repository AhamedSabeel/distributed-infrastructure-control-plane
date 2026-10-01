from abc import ABC, abstractmethod
from typing import Any


class InfrastructureAdapter(ABC):

    @abstractmethod
    def create_resource(
        self,
        resource_name: str,
        desired_state: dict[str, Any],
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def delete_resource(
        self,
        resource_name: str,
    ) -> bool:
        pass

    @abstractmethod
    def get_observed_state(
        self,
        resource_name: str,
        desired_state: dict[str, Any],
    ) -> dict[str, Any]:
        pass
