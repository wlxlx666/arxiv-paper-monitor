import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # 邮箱配置
    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

    # 本地测试：设为 false 时不实际发信，把邮件内容打印到控制台
    SEND_EMAIL = os.getenv("SEND_EMAIL", "true").lower() in ("1", "true", "yes")

    # === AI 精读（DeepSeek）配置 ===
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    # 每天挑选重要性最高的前 N 篇论文下载 PDF 全文精读
    PDF_READ_COUNT = int(os.getenv("PDF_READ_COUNT", 5))
    # 提取 PDF 前几页正文用于精读
    PDF_PAGES = int(os.getenv("PDF_PAGES", 6))
    # 未精读论文在邮件中展示的摘要长度上限
    MAX_ABSTRACT_CHARS = int(os.getenv("MAX_ABSTRACT_CHARS", 800))
    
    # === 新增：时间限制变量 ===
    # 优先从环境变量读取，默认为 1 天。如果设为 0 则表示无时间限制。
    FETCH_DAYS = int(os.getenv("FETCH_DAYS", 1))
    
    # Arxiv配置
    _env_keywords = os.getenv("SEARCH_KEYWORDS")
    if _env_keywords:
        SEARCH_KEYWORDS = [kw.strip().strip('"').strip("'") for kw in _env_keywords.split(",")]
    else:
        SEARCH_KEYWORDS = [
            "Rydberg atom",
            "magneto-optical trap",
            "optical tweezers",
            "nanophotonics",
            "micro cavity",
            "cavity QED"
        ]
        
    MAX_RESULTS = int(os.getenv("MAX_RESULTS", 50))
    
    # 定时任务配置
    SCHEDULE_TIME = "09:00"  
    TEST_MODE = False  
    
    # 日志配置
    LOG_FILE = "logs/arxiv_digest.log"
    
    @classmethod
    def validate(cls):
        # 本地测试模式（SEND_EMAIL=false）不需要邮箱密钥
        if not cls.SEND_EMAIL:
            return True
        if not cls.EMAIL_SENDER or not cls.EMAIL_PASSWORD:
            raise ValueError("邮箱配置不完整，请检查 .env 文件或 GitHub Secrets")
        return True
