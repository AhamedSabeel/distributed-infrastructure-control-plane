import logging
import time
from datetime import datetime, timezone

from app.database.database import SessionLocal
from app.models.resource import Resource
from app.reconciler.reconciliation import ReconciliationService


logger = logging.getLogger(__name__)


class ReconciliationController:

    def __init__(self, interval: int = 5):
        self.interval = interval
        self.running = True

    def run(self):

        logger.info(
            "Reconciliation controller started"
        )

        while self.running:

            db = SessionLocal()

            try:

                now = datetime.now(timezone.utc)

                resources = (
                    db.query(Resource)
                    .filter(
                        Resource.status.notin_(
                            ["DELETED", "FAILED"]
                        ),
                        (
                            (Resource.next_retry_at.is_(None))
                            | (
                                Resource.next_retry_at
                                <= now
                            )
                        ),
                    )
                    .all()
                )

                logger.info(
                    "Found %d resource(s) to reconcile",
                    len(resources),
                )

                ordered_resources = (
                    self._order_by_dependencies(
                        resources
                    )
                )

                logger.info(
                    "Reconciliation order: %s",
                    [
                        resource.name
                        for resource in ordered_resources
                    ],
                )

                for resource in ordered_resources:

                    logger.info(
                        "Reconciling resource: %s "
                        "(status=%s)",
                        resource.name,
                        resource.status,
                    )

                    reconciler = ReconciliationService(
                        db
                    )

                    reconciler.reconcile(
                        resource
                    )

            except Exception:

                logger.exception(
                    "Controller loop failed"
                )

            finally:

                db.close()

            time.sleep(
                self.interval
            )

    @staticmethod
    def _order_by_dependencies(
        resources: list[Resource],
    ) -> list[Resource]:

        resource_map = {
            resource.name: resource
            for resource in resources
        }

        # Number of dependencies that must be processed first.
        in_degree = {
            resource.name: 0
            for resource in resources
        }

        # dependency -> dependent resources
        dependents = {
            resource.name: []
            for resource in resources
        }

        for resource in resources:

            dependencies = (
                resource.dependencies or []
            )

            for dependency in dependencies:

                # Missing dependencies are handled
                # by the reconciliation service.
                if dependency not in resource_map:
                    continue

                in_degree[resource.name] += 1

                dependents[dependency].append(
                    resource.name
                )

        # Start with resources that have no dependencies.
        queue = sorted(
            [
                name
                for name, degree in in_degree.items()
                if degree == 0
            ]
        )

        ordered_names = []

        while queue:

            current = queue.pop(0)

            ordered_names.append(
                current
            )

            for dependent in sorted(
                dependents[current]
            ):

                in_degree[dependent] -= 1

                if in_degree[dependent] == 0:

                    queue.append(
                        dependent
                    )

            queue.sort()

        # Cycle detection
        if len(ordered_names) != len(resources):

            cyclic_resources = [
                name
                for name, degree in in_degree.items()
                if degree > 0
            ]

            logger.error(
                "Dependency cycle detected involving: %s",
                cyclic_resources,
            )

            # Keep cyclic resources at the end.
            ordered_names.extend(
                sorted(
                    cyclic_resources
                )
            )

        return [
            resource_map[name]
            for name in ordered_names
        ]

    def stop(self):

        self.running = False
