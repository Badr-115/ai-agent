import os
import subprocess
import logging
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class FullyAutonomousBuilder:
    def __init__(self, repo_url: str = None):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("❌ خطأ: مفتاح GEMINI_API_KEY غير موجود في ملف .env!")
            
        self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-1.5-flash"
        self.repo_url = repo_url
        logger.info("🤖 تم تهيئة الأجينت المستقل بنجاح وجاهز لتنفيذ طلباتك بالكامل!")

    def execute_terminal(self, command: str) -> str:
        logger.info(f"💻 تنفيذ أمر النظام: {command}")
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
            output = result.stdout.strip() + "\n" + result.stderr.strip()
            return output if output else "تم التنفيذ بنجاح."
        except Exception as e:
            return f"خطأ في تنفيذ الأمر: {str(e)}"

    def create_file(self, filepath: str, content: str) -> str:
        logger.info(f"📄 إنشاء ملف وتدقيقه: {filepath}")
        try:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content.strip())
            return f"تم حفظ الملف بنجاح: {filepath}"
        except Exception as e:
            return f"فشل إنشاء الملف: {str(e)}"

    def run_project_pipeline(self, user_requirement: str, project_folder: str = "my_auto_project"):
        logger.info(f"\n🚀 بدء بناء المشروع بناءً على طلبك:")
        logger.info(f"📌 المتطلبات: {user_requirement}\n")
        
        # تجهيز المجلد
        os.makedirs(project_folder, exist_ok=True)
        os.chdir(project_folder)
        
        # تهيئة Git محلياً إن لم يكن موجوداً
        if not os.path.exists(".git"):
            self.execute_terminal("git init")
            if self.repo_url:
                self.execute_terminal(f"git remote add origin {self.repo_url}")

        system_instruction = f"""
        أنت مهندس برمجيات ذكاء اصطناعي مستقل بالكامل وعالي الكفاءة.
        مهمتك هي بناء مشروع كامل من الصفر بناءً على متطلبات المستخدم بدقة، مع مراجعة الأخطاء وتصحيحها.
        
        متطلبات المشروع الأساسية من المستخدم:
        "{user_requirement}"

        لديك الصلاحية لإنشاء الملفات، تشغيل الاختبارات، وإدارة مستودع الكود.
        استخدم حصرياً هذه الوسوم لتنفيذ المهام:
        1. لإنشاء أو كتابة ملف داخل المجلد:
           [FILE: relative/path/to/file.ext]
           محتوى الملف هنا...
           [/FILE]
        2. لتنفيذ أي أمر في الطرفية (مثل اختبار الأكواد، تثبيت حزم، أو أوامر Git):
           [RUN] أمر الطرفية هنا [/RUN]
        3. عند إتمام المشروع بالكامل، مراجعته، والتأكد من خلوه من الأخطاء ورفعه للمستودع:
           [DONE]

        الرجاء التخطيط بعناية، كتابة أكواد نظيفة واحترافية، فحص الأخطاء، ثم رفع التغييرات إلى غيتهاب تلقائياً عبر الأوامر (git add, git commit, git push).
        """

        current_prompt = system_instruction
        
        for step in range(12):
            logger.info(f"--- [الخطوة التشغيلية {step + 1}] الأجينت يحلل، يكتب، ويدقق... ---")
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=current_prompt,
            )
            
            reply = response.text
            print(f"\n🤖 رد الأجينت:\n{reply}\n")
            
            if "[DONE]" in reply:
                logger.info("🎉 تم إنجاز المشروع بالكامل، مراجعته، ورفع التغييرات إلى المستودع بدون أي تدخل منك!")
                break
                
            feedback = ""
            
            # معالجة الملفات المنشأة
            files = re.findall(r'\[FILE:\s*(.*?)\](.*?)\[/FILE\]', reply, re.DOTALL)
            for path, content in files:
                res = self.create_file(path.strip(), content)
                feedback += f"{res}\n"
                
            # معالجة الأوامر والطرفية
            commands = re.findall(r'\[RUN\](.*?)\[/RUN\]', reply, re.DOTALL)
            for cmd in commands:
                res = self.execute_terminal(cmd.strip())
                feedback += f"نتيجة تنفيذ `{cmd.strip()}`:\n{res}\n"
                
            if feedback:
                current_prompt = f"النتائج والتقارير للخطوة السابقة:\n{feedback}\nتابع العمل، صحح أي أخطاء ظهرت، واصل حتى تنهي المشروع وتدفعه للمستودع وتكتب [DONE]."
            else:
                current_prompt = "لم تقم بأي إجراء برمجي أو كتابة [DONE]. يرجى المتابعة وكتابة الأكواد والملفات المطلوبة."

        # العودة للمجلد الرئيسي
        os.chdir("..")

if __name__ == "__main__":
    # ضع رابط مستودعك هنا أو اتركه فارغاً وسيتم إنشاؤه محلياً
    GITHUB_REPO = "https://github.com/Badr-115/my-universe.git" # يمكنك تعديله لرابط مستودعك
    
    # حدد طلبك أو مشروعك بدقة هنا:
    my_exact_request = """
    أريد بناء تطبيق ويب متكامل لإدارة المهام (Task Manager) باستخدام React و Tailwind CSS و FastAPI في الباك إند،
    مع قاعدة بيانات محلية، وتصميم أنيق وعصري، وتوثيق كامل في ملف README.md، 
    ثم عمل git add و git commit و git push لرفعه بشكل كامل إلى المستودع الخاص بي بدون أي تدخل مني.
    """
    
    builder = FullyAutonomousBuilder(repo_url=GITHUB_REPO)
    builder.run_project_pipeline(user_requirement=my_exact_request)
