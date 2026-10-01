from typing import Any

import docker
from docker.errors import DockerException

from app.infrastructure.base import InfrastructureAdapter


class DockerAdapter(InfrastructureAdapter):

    def __init__(self):
        self.client = docker.from_env()

    def create_resource(
        self,
        resource_name: str,
        desired_state: dict[str, Any],
    ) -> dict[str, Any]:

        image = desired_state.get(
            "image",
            "nginx:latest",
        )

        replicas = int(
            desired_state.get(
                "replicas",
                1,
            )
        )

        containers = self._get_containers(
            resource_name
        )

        container_map = {
            container.name: container
            for container in containers
        }

        desired_names = {
            f"{resource_name}-{index}"
            for index in range(1, replicas + 1)
        }

        created = []
        restarted = []
        removed = []

        for container_name in sorted(desired_names):

            container = container_map.get(
                container_name
            )

            if container is None:

                self.client.images.pull(image)

                self.client.containers.run(
                    image,
                    name=container_name,
                    detach=True,
                    labels={
                        "control-plane-resource": resource_name
                    },
                )

                created.append(container_name)

                continue

            current_image = container.attrs["Config"]["Image"]

            # Image drift
            if current_image != image:

                try:
                    container.remove(
                        force=True
                    )
                except DockerException:
                    pass

                self.client.images.pull(image)

                self.client.containers.run(
                    image,
                    name=container_name,
                    detach=True,
                    labels={
                        "control-plane-resource": resource_name
                    },
                )

                restarted.append(container_name)

                continue

            # Same image but container is stopped
            if container.status != "running":

                try:
                    container.start()
                    restarted.append(container_name)

                except DockerException:

                    try:
                        container.remove(
                            force=True
                        )
                    except DockerException:
                        pass

                    self.client.containers.run(
                        image,
                        name=container_name,
                        detach=True,
                        labels={
                            "control-plane-resource": resource_name
                        },
                    )

                    restarted.append(container_name)

        # Remove excess replicas
        for container_name, container in container_map.items():

            if container_name not in desired_names:

                try:
                    container.remove(
                        force=True
                    )

                    removed.append(container_name)

                except DockerException:
                    pass

        return {
            "resource_name": resource_name,
            "desired_replicas": replicas,
            "created": created,
            "restarted": restarted,
            "removed": removed,
        }

    def delete_resource(
        self,
        resource_name: str,
    ) -> bool:

        containers = self._get_containers(
            resource_name
        )

        for container in containers:

            try:
                container.remove(
                    force=True
                )

            except DockerException:
                return False

        return True

    def get_observed_state(
        self,
        resource_name: str,
        desired_state: dict[str, Any],
    ) -> dict[str, Any]:

        containers = self._get_containers(
            resource_name
        )

        running_containers = []
        stopped_containers = []
        container_details = []

        for container in containers:

            image = (
                container.attrs["Config"]["Image"]
            )

            details = {
                "name": container.name,
                "status": container.status,
                "image": image,
            }

            container_details.append(details)

            if container.status == "running":
                running_containers.append(
                    container.name
                )
            else:
                stopped_containers.append(
                    container.name
                )

        return {
            "resource_name": resource_name,
            "running_replicas": len(
                running_containers
            ),
            "stopped_replicas": len(
                stopped_containers
            ),
            "total_replicas": len(containers),
            "containers": running_containers,
            "stopped_containers": stopped_containers,
            "container_details": container_details,
        }

    def _get_containers(
        self,
        resource_name: str,
    ):
        return self.client.containers.list(
            all=True,
            filters={
                "label": (
                    f"control-plane-resource="
                    f"{resource_name}"
                )
            },
        )
