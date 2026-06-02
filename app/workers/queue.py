"""
Clinova Penthus AI Engine - Job Queue
Simple async job queue for background processing.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class Job:
    """Represents a background job."""

    def __init__(
        self,
        job_type: str,
        payload: Dict[str, Any],
        max_retries: int = 3,
        delay_seconds: float = 0,
    ):
        self.id = str(uuid.uuid4())
        self.type = job_type
        self.payload = payload
        self.status = JobStatus.PENDING
        self.max_retries = max_retries
        self.retry_count = 0
        self.delay_seconds = delay_seconds
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
        }


class JobQueue:
    """In-memory async job queue."""

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: Dict[str, Job] = {}
        self._handlers: Dict[str, Callable[[Job], Coroutine]] = {}
        self._running = False
        self._workers: List[asyncio.Task] = []

    def register_handler(self, job_type: str, handler: Callable[[Job], Coroutine]) -> None:
        """Register a handler for a job type."""
        self._handlers[job_type] = handler
        logger.debug("job_handler_registered", job_type=job_type)

    async def enqueue(self, job: Job) -> str:
        """Add a job to the queue."""
        self._jobs[job.id] = job
        await self._queue.put(job)
        logger.debug("job_enqueued", job_id=job.id, type=job.type)
        return job.id

    async def start(self) -> None:
        """Start worker tasks."""
        self._running = True
        for i in range(self.max_workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        logger.info("job_queue_started", workers=self.max_workers)

    async def stop(self) -> None:
        """Stop worker tasks."""
        self._running = False
        # Cancel all workers
        for task in self._workers:
            task.cancel()
        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("job_queue_stopped")

    async def _worker(self, worker_id: int) -> None:
        """Worker task that processes jobs."""
        logger.debug("queue_worker_started", worker_id=worker_id)

        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            handler = self._handlers.get(job.type)
            if not handler:
                logger.warning("no_handler_for_job", job_type=job.type, job_id=job.id)
                job.status = JobStatus.FAILED
                job.error = f"No handler registered for job type: {job.type}"
                continue

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)

            try:
                if job.delay_seconds > 0:
                    await asyncio.sleep(job.delay_seconds)
                await handler(job)
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                logger.debug("job_completed", job_id=job.id, type=job.type)
            except Exception as e:
                job.retry_count += 1
                if job.retry_count < job.max_retries:
                    job.status = JobStatus.RETRYING
                    job.delay_seconds = min(2 ** job.retry_count, 300)  # Exponential backoff
                    await self._queue.put(job)
                    logger.warning(
                        "job_retrying",
                        job_id=job.id,
                        type=job.type,
                        retry=job.retry_count,
                        error=str(e),
                    )
                else:
                    job.status = JobStatus.FAILED
                    job.error = str(e)
                    logger.error(
                        "job_failed",
                        job_id=job.id,
                        type=job.type,
                        error=str(e),
                    )

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        job_type: Optional[str] = None,
        status: Optional[JobStatus] = None,
    ) -> List[Job]:
        """List jobs with optional filtering."""
        jobs = self._jobs.values()
        if job_type:
            jobs = [j for j in jobs if j.type == job_type]
        if status:
            jobs = [j for j in jobs if j.status == status]
        return list(jobs)
