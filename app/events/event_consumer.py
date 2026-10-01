from datetime import datetime, timezone
import json
import logging
import time

import redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.config import settings
from app.database.database import SessionLocal
from app.events.event_service import EventService
from app.models.resource import Resource
from app.reconciler.reconciliation import ReconciliationService


logger = logging.getLogger(__name__)


class EventConsumer:
    GROUP_NAME = "control-plane-controllers"
    CONSUMER_NAME = "controller-1"

    def __init__(self):
        self.redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=None,
            socket_connect_timeout=5,
            health_check_interval=30,
        )

        self.stream = EventService.STREAM_NAME

        self._create_consumer_group()

    def _create_consumer_group(self):
        try:
            self.redis.xgroup_create(
                self.stream,
                self.GROUP_NAME,
                id="0",
                mkstream=True,
            )

            logger.info(
                "Created consumer group %s",
                self.GROUP_NAME,
            )

        except redis.exceptions.ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def run(self):
        logger.info("Event consumer started")

        while True:
            try:
                messages = self.redis.xreadgroup(
                    groupname=self.GROUP_NAME,
                    consumername=self.CONSUMER_NAME,
                    streams={
                        self.stream: ">"
                    },
                    count=10,
                    block=5000,
                )

                if not messages:
                    continue

                for stream_name, events in messages:
                    for event_id, fields in events:
                        self.process_event(
                            event_id,
                            fields,
                        )

            except RedisError:
                logger.exception(
                    "Redis event consumption failed"
                )

                time.sleep(2)

    def process_event(
        self,
        event_id: str,
        fields: dict,
    ):
        try:
            event = json.loads(
                fields["data"]
            )

            event_type = event["event_type"]
            resource_id = event["resource_id"]

            logger.info(
                "Processing event %s: %s",
                event_id,
                event_type,
            )

            db: Session = SessionLocal()

            try:
                resource = (
                    db.query(Resource)
                    .filter(
                        Resource.id == resource_id
                    )
                    .first()
                )

                if not resource:
                    logger.warning(
                        "Resource %s not found",
                        resource_id,
                    )

                    self.redis.xack(
                        self.stream,
                        self.GROUP_NAME,
                        event_id,
                    )

                    return

                if resource.status == "FAILED":
                    logger.warning(
                        "Skipping failed resource %s",
                        resource.name,
                    )

                    self.redis.xack(
                        self.stream,
                        self.GROUP_NAME,
                        event_id,
                    )

                    return

                if (
                    resource.next_retry_at is not None
                    and resource.next_retry_at
                    > datetime.now(timezone.utc)
                ):
                    logger.info(
                        "Skipping resource %s; retry scheduled for %s",
                        resource.name,
                        resource.next_retry_at,
                    )

                    self.redis.xack(
                        self.stream,
                        self.GROUP_NAME,
                        event_id,
                    )

                    return

                reconciler = ReconciliationService(db)

                reconciler.reconcile(
                    resource
                )

            finally:
                db.close()

            self.redis.xack(
                self.stream,
                self.GROUP_NAME,
                event_id,
            )

        except Exception:
            logger.exception(
                "Failed to process event %s",
                event_id,
            )
