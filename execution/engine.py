from loguru import logger
from core.schemas import Task, TaskStatus
import asyncio

class ExecutionEngine:
    async def execute_task(self, task: Task) -> bool:
        task.status = TaskStatus.IN_PROGRESS
        logger.info(f"جاري تنفيذ المهمة: {task.description}")
        
        try:
            await asyncio.sleep(1) # محاكاة للوقت
            task.result = "تم التنفيذ بنجاح."
            task.status = TaskStatus.COMPLETED
            logger.success("اكتملت المهمة.")
            return True
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
            logger.error("فشلت المهمة.")
            return False
