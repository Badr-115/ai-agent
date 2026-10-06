import asyncio
import os
from dotenv import load_dotenv
from providers.groq_provider import GroqProvider
from agents.orchestrator import AgentOrchestrator

async def main():
    load_dotenv()
    
    if not os.getenv("GROQ_API_KEY"):
        print("الرجاء وضع مفتاح GROQ في ملف .env أولاً!")
        return

    provider = GroqProvider()
    orchestrator = AgentOrchestrator(provider=provider)
    
    # رسالة لاختبار النظام
    await orchestrator.process_request("ابحث عن الملفات الموجودة في مشروعي.")

if __name__ == "__main__":
    asyncio.run(main())
