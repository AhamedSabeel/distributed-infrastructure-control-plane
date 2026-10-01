import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.infrastructure.docker_adapter import DockerAdapter
from app.models.resource import Resource
from app.services.history_service import record_history
from app.services.state_transition_service import validate_transition

logger = logging.getLogger(__name__)


class ReconciliationService:

    def __init__(self, db: Session):
        self.db = db
        self.infrastructure = DockerAdapter()

    def _set_status(
        self,
        resource: Resource,
        new_status: str,
    ) -> None:

        if resource.status == new_status:
            return

        validate_transition(
            resource,
            new_status,
        )

        old_status = resource.status

        resource.status = new_status

        logger.info(
            "Resource %s state transition: %s -> %s",
            resource.name,
            old_status,
            new_status,
        )

    def reconcile(self, resource: Resource):

        logger.info(
            "Starting reconciliation for %s",
            resource.name,
        )

        # ---------------------------------------------------------
        # DELETE LIFECYCLE
        # ---------------------------------------------------------
        if resource.status == "DELETING":

            logger.info(
                "Deleting infrastructure for %s",
                resource.name,
            )

            try:
                deleted = self.infrastructure.delete_resource(
                    resource.name
                )

                if deleted:
                    record_history(
                        self.db,
                        resource,
                        event_type="RESOURCE_DELETED",
                        message="Infrastructure removed successfully",
                    )

                    self.db.delete(resource)
                    self.db.commit()

                    logger.info(
                        "Resource %s completely deleted",
                        resource.name,
                    )

                else:
                    self._set_status(
			resource,
			"FAILED",
                    )
                    resource.last_error = (
                        "Failed to remove infrastructure"
                    )

                    record_history(
                        self.db,
                        resource,
                        event_type="DELETE_FAILED",
                        message="Infrastructure cleanup failed",
                    )

                    self.db.commit()

            except Exception as error:

                self.db.rollback()

                self._set_status(
 	            resource,
                    "FAILED",
                )
                resource.last_error = str(error)

                self.db.commit()

                logger.exception(
                    "Deletion failed for %s",
                    resource.name,
                )

            return



        # ---------------------------------------------------------
        # DEPENDENCY CHECK
        # ---------------------------------------------------------
        dependencies = resource.dependencies or []

        if dependencies:

            dependency_resources = (
                self.db.query(Resource)
                .filter(
                    Resource.name.in_(dependencies)
                )
                .all()
            )

            dependency_map = {
                dependency.name: dependency
                for dependency in dependency_resources
            }

            missing_dependencies = [
                dependency
                for dependency in dependencies
                if dependency not in dependency_map
            ]

            if missing_dependencies:

                self._set_status(
                    resource,
                    "BLOCKED",
                )
                resource.last_error = (
                    "Missing dependencies: "
                    + ", ".join(missing_dependencies)
                )

                record_history(
                    self.db,
                    resource,
                    event_type="DEPENDENCY_BLOCKED",
                    message=resource.last_error,
                )

                self.db.commit()

                logger.warning(
                    "Resource %s blocked by missing dependencies: %s",
                    resource.name,
                    missing_dependencies,
                )

                return

            not_ready_dependencies = [
                dependency
                for dependency in dependencies
                if dependency_map[dependency].status != "READY"
            ]

            if not_ready_dependencies:

                self._set_status(
                    resource,
                    "BLOCKED",
                )
                resource.last_error = (
                    "Dependencies not ready: "
                    + ", ".join(not_ready_dependencies)
                )

                record_history(
                    self.db,
                    resource,
                    event_type="DEPENDENCY_BLOCKED",
                    message=resource.last_error,
                )

                self.db.commit()

                logger.info(
                    "Resource %s waiting for dependencies: %s",
                    resource.name,
                    not_ready_dependencies,
                )

                return

            logger.info(
                "All dependencies are READY for %s",
                resource.name,
            )





        # ---------------------------------------------------------
        # NORMAL RECONCILIATION
        # ---------------------------------------------------------
        try:

            desired_state = resource.desired_state

            observed_state = (
                self.infrastructure.get_observed_state(
                    resource_name=resource.name,
                    desired_state=desired_state,
                )
            )

            logger.info(
                "Observed state for %s: %s",
                resource.name,
                observed_state,
            )

            resource.observed_state = observed_state

            record_history(
                self.db,
                resource,
                event_type="STATE_OBSERVED",
                message="Infrastructure state observed",
            )

            # -----------------------------------------------------
            # CHECK CONVERGENCE
            # -----------------------------------------------------
            if self._is_converged(
                desired_state,
                observed_state,
            ):

                self._set_status(
                    resource,
                    "READY",
                )
                resource.last_error = None
                resource.retry_count = 0
                resource.next_retry_at = None

                record_history(
                    self.db,
                    resource,
                    event_type="RECONCILIATION_SUCCESS",
                    message="Desired and observed state are converged",
                )

                self.db.commit()

                logger.info(
                    "Resource %s is READY",
                    resource.name,
                )

                return

            # -----------------------------------------------------
            # DRIFT DETECTED
            # -----------------------------------------------------
            self._set_status(
                resource,
                "RECONCILING",
            )

            record_history(
                self.db,
                resource,
                event_type="DRIFT_DETECTED",
                message="Observed state does not match desired state",
            )

            self.db.commit()

            logger.warning(
                "DRIFT DETECTED for %s",
                resource.name,
            )

            # -----------------------------------------------------
            # APPLY DESIRED STATE
            # -----------------------------------------------------
            self.infrastructure.create_resource(
                resource_name=resource.name,
                desired_state=desired_state,
            )

            # -----------------------------------------------------
            # OBSERVE AGAIN
            # -----------------------------------------------------
            observed_state = (
                self.infrastructure.get_observed_state(
                    resource_name=resource.name,
                    desired_state=desired_state,
                )
            )

            resource.observed_state = observed_state

            # -----------------------------------------------------
            # FINAL CONVERGENCE CHECK
            # -----------------------------------------------------
            if self._is_converged(
                desired_state,
                observed_state,
            ):

                self._set_status(
                    resource,
                    "READY",
                )
                resource.last_error = None
                resource.retry_count = 0
                resource.next_retry_at = None

                record_history(
                    self.db,
                    resource,
                    event_type="RECONCILIATION_SUCCESS",
                    message="Resource successfully reconciled",
                )

                logger.info(
                    "Resource %s successfully reconciled",
                    resource.name,
                )

            else:

                self._set_status(
                    resource,
                    "DRIFTED",
                )

                record_history(
                    self.db,
                    resource,
                    event_type="RECONCILIATION_INCOMPLETE",
                    message="Resource remains drifted after reconciliation",
                )

                logger.warning(
                    "Resource %s remains DRIFTED",
                    resource.name,
                )

            self.db.commit()

        # ---------------------------------------------------------
        # RETRY / EXPONENTIAL BACKOFF
        # ---------------------------------------------------------
        except Exception as error:

            self.db.rollback()

            # Refresh the resource so retry fields are current.
            self.db.refresh(resource)

            resource.retry_count += 1

            if resource.retry_count >= resource.max_retries:

                self._set_status(
                    resource,
                    "FAILED",
                )
                resource.next_retry_at = None

                message = (
                    f"Maximum retries reached: "
                    f"{resource.retry_count}"
                )

            else:

                self._set_status(
                    resource,
                    "RECONCILING",
                )

                delay = 2 ** resource.retry_count

                resource.next_retry_at = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=delay)
                )

                message = (
                    f"Reconciliation failed. "
                    f"Retry {resource.retry_count}/"
                    f"{resource.max_retries} "
                    f"scheduled in {delay} seconds"
                )

            resource.last_error = str(error)

            record_history(
                self.db,
                resource,
                event_type="RECONCILIATION_FAILED",
                message=message,
            )

            self.db.commit()

            logger.exception(
                "Reconciliation failed for %s",
                resource.name,
            )

    @staticmethod
    def _is_converged(
        desired_state: dict,
        observed_state: dict,
    ) -> bool:

        desired_replicas = int(
            desired_state.get("replicas", 1)
        )

        desired_image = desired_state.get(
            "image"
        )

        actual_replicas = int(
            observed_state.get(
                "running_replicas",
                0,
            )
        )

        if desired_replicas != actual_replicas:
            return False

        if not desired_image:
            return True

        container_details = observed_state.get(
            "container_details",
            [],
        )

        for container in container_details:

            if container["status"] != "running":
                return False

            if container["image"] != desired_image:
                return False

        return True
