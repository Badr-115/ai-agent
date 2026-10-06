from loguru import logger
from core.schemas import Plan
from providers.base import LLMProvider
from execution.engine import ExecutionEngine

class AgentOrchestrator:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.engine = ExecutionEngine()
        
    async def process_request(self, user_request: str):
        logger.info("يتم الآن تحليل طلبك وبناء الخطة...")
        prompt = f"Create an execution plan for: '{user_request}'"
        
        plan = await self.provider.generate_structured(
            prompt=prompt,
            schema=Plan,
            system_prompt="Break down tasks logically into a plan."
        )
        
        logger.info(f"تم إنشاء الخطة وتتضمن {len(plan.tasks)} مهام.")
        
        for task in plan.tasks:
            await self.engine.execute_task(task)
            
        logger.info("انتهت العملية بالكامل.")
