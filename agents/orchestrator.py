from loguru import logger
from core.schemas import Plan
from providers.base import LLMProvider
from execution.engine import ExecutionEngine, TaskExecutor


class AgentOrchestrator:
    def __init__(self, provider: LLMProvider, executor: TaskExecutor | None = None):
        self.provider = provider
        self.engine = ExecutionEngine(executor)

    async def process_request(self, user_request: str):
        logger.info("Planning request...")
        plan = await self.provider.generate_structured(
            prompt=f"Create an execution plan for: {user_request!r}",
            schema=Plan,
            system_prompt="Break down tasks logically into a plan.",
        )
        logger.info("Plan contains {} tasks", len(plan.tasks))
        for task in plan.tasks:
            await self.engine.execute_task(task)
        return plan
