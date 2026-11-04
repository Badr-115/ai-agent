from collections.abc import Awaitable, Callable
from loguru import logger

from core.schemas import Task, TaskStatus

# An executor must be explicitly supplied by the caller. No simulation is
# described as a completed task.
TaskExecutor = Callable[[Task], Awaitable[str]]


class ExecutionEngine:
    def __init__(self, executor: TaskExecutor | None = None):
        self.executor = executor

    async def execute_task(self, task: Task) -> bool:
        task.status = TaskStatus.IN_PROGRESS
        task.result = None
        task.error = None
        if self.executor is None:
            task.status = TaskStatus.FAILED
            task.error = "No task executor configured; task was not executed."
            logger.warning("Task %s was not executed", task.id)
            return False
        try:
            result = await self.executor(task)
            if not isinstance(result, str) or not result.strip():
                raise ValueError("Task executor did not return a verifiable result")
            task.result = result
            task.status = TaskStatus.COMPLETED
            return True
        except Exception as exc:
            task.error = f"{type(exc).__name__}: {exc}"
            task.status = TaskStatus.FAILED
            logger.error("Task %s failed: %s", task.id, task.error)
            return False
