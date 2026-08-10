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

    # === 作者代表作（Semantic Scholar / arXiv）配置 ===
    # Semantic Scholar API 请求超时（秒）
    SEMANTIC_SCHOLAR_TIMEOUT = int(os.getenv("SEMANTIC_SCHOLAR_TIMEOUT", 10))
    # 每篇论文最多查几个关键作者的代表作
    MAX_AUTHOR_PROFILES = int(os.getenv("MAX_AUTHOR_PROFILES", 5))
    
    # === 时间限制变量 ===
    # 搜索时间范围，单位小时。默认取当前运行时间前 26 小时。
    # 未设置 FETCH_HOURS 时回退到旧的 FETCH_DAYS（天）配置，两者都未设置则默认 26 小时。
    _fetch_hours = os.getenv("FETCH_HOURS")
    if _fetch_hours:
        FETCH_HOURS = int(_fetch_hours)
    elif os.getenv("FETCH_DAYS"):
        FETCH_HOURS = int(os.getenv("FETCH_DAYS")) * 24
    else:
        FETCH_HOURS = 26
    
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
