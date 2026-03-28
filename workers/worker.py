"""
OmniDrop AI — Temporal Worker Entrypoint

Connects to the Temporal server and starts polling the task queue.
Run with: python worker.py
"""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from shared.constants import TEMPORAL_TASK_QUEUE
from workers.activities.document_activities import extract_documents, sync_to_database
from workers.workflows.intake_workflow import IntakeWorkflow

logger = logging.getLogger(__name__)


async def main() -> None:
    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", TEMPORAL_TASK_QUEUE)

    logger.info(f"Connecting to Temporal at {temporal_host} (namespace: {temporal_namespace})")

    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[IntakeWorkflow],
        activities=[extract_documents, sync_to_database],
    )

    logger.info(f"Worker started — polling queue: {task_queue}")
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
