import json
import logging
from typing import Any

import redis

from app.config import settings


logger = logging.getLogger(__name__)


class EventService:

    STREAM_NAME = "control-plane-events"

    def __init__(self):
        self.redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    def publish(
        self,
        event_type: str,
        resource_id: str,
    ) -> str:

        event = {
            "event_type": event_type,
            "resource_id": resource_id,
        }

        event_id = self.redis.xadd(
            self.STREAM_NAME,
            {
                "data": json.dumps(event),
            },
        )

        logger.info(
            "Published event %s for resource %s",
            event_type,
            resource_id,
        )

        return event_id
