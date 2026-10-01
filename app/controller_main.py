import logging

from app.controllers.reconciliation_controller import (
    ReconciliationController,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s "
        "%(message)s"
    ),
)


if __name__ == "__main__":
    controller = ReconciliationController(
        interval=5
    )

    controller.run()
