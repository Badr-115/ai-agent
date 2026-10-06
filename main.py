import asyncio
import os
from dotenv import load_dotenv
from providers.gemini_provider import GeminiProvider
from agents.orchestrator import AgentOrchestrator

async def main():
    load_dotenv()
    
    if not os.getenv("GEMINI_API_KEY"):
        print("الرجاء وضع GEMINI_API_KEY في ملف .env أولاً!")
        return

    provider = GeminiProvider()
    orchestrator = AgentOrchestrator(provider=provider)
    
    # رسالة لاختبار النظام
    await orchestrator.process_request("ابحث عن الملفات الموجودة في مشروعي.")

if __name__ == "__main__":
    asyncio.run(main())
