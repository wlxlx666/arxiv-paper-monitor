# main.py - 适配GitHub Actions的版本
import sys
import time
import os
from datetime import datetime
import logging

# Windows 控制台默认 GBK，会因 emoji 打印崩溃；统一改用 UTF-8 输出
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from config import Config
from arxiv_fetcher import ArxivFetcher
from email_sender import EmailSender
from llm_summarizer import LLMSummarizer
from author_profiles import AuthorProfiles

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ArxivDailyDigest:
    def __init__(self):
        self.fetcher = ArxivFetcher()
        self.email_sender = EmailSender()
        self.summarizer = LLMSummarizer()
        self.author_profiles = AuthorProfiles()

    def run(self, test_mode=False):
        """运行一次任务"""
        logger.info("=" * 60)
        logger.info(f"开始执行Arxiv论文抓取任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"AI精读引擎: {'已启用(DeepSeek)' if self.summarizer.enabled else '未启用(将直接展示原始摘要)'}")

        try:
            # 1. 获取论文
            # === 修改：按小时窗口抓取（默认当前时间前 28 小时） ===
            days_back = 0 if test_mode else None
            hours_back = None if test_mode else getattr(Config, 'FETCH_HOURS', 28)
            papers = self.fetcher.fetch_recent_papers(days_back=days_back, hours_back=hours_back)

            # 2. 生成摘要
            summaries = []
            if papers:
                papers, summaries = self._enrich_papers(papers)
                logger.info(f"找到 {len(papers)} 篇相关论文")
            else:
                logger.info("今日没有找到相关论文，将发送『无新论文』通知")

            # 3. 总是发送邮件（无论有无论文）
            success = self.email_sender.send_digest(papers, summaries)

            if success:
                if papers:
                    logger.info(f"✅ 任务完成！成功发送 {len(papers)} 篇论文摘要")
                else:
                    logger.info("✅ 任务完成！已发送『今日无新论文』通知")
            else:
                logger.error("邮件发送失败")

        except Exception as e:
            logger.exception(f"任务执行失败: {e}")

        logger.info("=" * 60)

    def _enrich_papers(self, papers: list):
        """AI 打分 → 挑 Top N 精读全文 → 拼装每篇摘要"""
        # 第一步：AI 批量打分（读摘要），得到 importance 和 reason
        scores = self.summarizer.score_papers(papers)
        for i, paper in enumerate(papers):
            s = scores.get(i, {})
            paper['importance'] = s.get('importance', 3)
            paper['reason'] = s.get('reason', '')
            paper['ai_summary'] = None
            paper['highlights'] = []
            paper['is_top'] = False
            paper['full_text_read'] = False

        if self.summarizer.enabled and scores:
            # 第二步：按 importance 选出精读名单
            pdf_read_count = getattr(Config, 'PDF_READ_COUNT', 5)
            deep_read_indexes = self.summarizer.select_top_for_deep_read(scores, pdf_read_count)
            logger.info(f"AI 挑选 {len(deep_read_indexes)} 篇论文下载全文精读")

            for idx in deep_read_indexes:
                if idx >= len(papers):
                    continue
                paper = papers[idx]
                full_text = self.fetcher.get_paper_full_text(paper)
                if full_text:
                    paper['full_text_read'] = True
                    paper['full_text'] = full_text  # 供作者画像解析复用，避免重复下载 PDF
                    result = self.summarizer.summarize_paper(paper, full_text)
                    if result:
                        paper['ai_summary'] = result['summary']
                        paper['highlights'] = result['highlights']
                        paper['importance'] = max(paper['importance'], 4)
                else:
                    logger.info(f"PDF 获取失败，降级为摘要总结: {paper['title'][:50]}")

        # 第三步：按 importance 排序，标记前 TOP_N 篇为今日最值得读
        top_n = getattr(Config, 'PDF_READ_COUNT', 5)
        papers.sort(key=lambda p: p.get('importance', 3), reverse=True)
        for paper in papers[:top_n]:
            paper['is_top'] = True

        # 第三步补充：为前 TOP_N 论文生成作者代表作 + 第一单位 + 图1
        # 有 DeepSeek key 时解析完整作者角色；无 key 时降级为 arXiv 第一作者 + Semantic Scholar 代表作
        for paper in papers[:top_n]:
            paper['author_profiles'] = self.author_profiles.build_author_profiles(paper, paper.get('full_text'))
            # 提取图 1（失败则 paper['figure1']=None，邮件不显示）
            paper['figure1'] = self.fetcher.extract_figure1(paper)

        # 第四步：组装邮件展示文本
        summaries = [self._build_paper_summary(p) for p in papers]
        return papers, summaries

    def _build_paper_summary(self, paper: dict) -> str:
        """生成单篇论文在邮件中的展示文本"""
        lines = [
            "=" * 60,
            f"📄 标题: {paper['title']}",
            "",
            f"👥 作者: {', '.join(paper['authors'][:3])}{' 等' if len(paper['authors']) > 3 else ''}",
            f"📅 发布时间: {paper['published']}",
            f"📚 分类: {paper['primary_category']}",
            f"🏷️ 命中关键词: {', '.join(paper.get('matched_keywords', ['未知']))}",
        ]
        if paper.get('reason'):
            lines.append(f"💡 AI 相关度: {paper['reason']} (重要性 {paper.get('importance', '?')}/5)")
        lines.append("")
        if paper.get('ai_summary'):
            lines.append("🤖 AI 中文总结:")
            lines.append(paper['ai_summary'])
            if paper.get('highlights'):
                lines.append("")
                lines.append("✨ 亮点:")
                for h in paper['highlights']:
                    lines.append(f"  • {h}")
        else:
            lines.append("📝 摘要:")
            lines.append(self._truncate_text(paper['abstract'], getattr(Config, 'MAX_ABSTRACT_CHARS', 800)))
            if paper.get('full_text_read'):
                lines.append("")
                lines.append("⚠️ AI 总结失败，以上为原文摘要")
        lines.append("")
        lines.append("🔗 链接:")
        lines.append(f"PDF: {paper['pdf_url']}")
        lines.append(f"Arxiv: {paper['arxiv_url']}")
        lines.append("=" * 60)
        lines.append("")
        return "\n".join(lines)

    def _truncate_text(self, text: str, max_length: int) -> str:
        """截断过长的文本，尽量在单词边界处截断"""
        text = text.replace('\n', ' ')
        if len(text) <= max_length:
            return text
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > 0:
            return truncated[:last_space]
        return truncated

    def run_once(self, test_mode=False):
        """
        单次运行模式 - 用于GitHub Actions
        执行一次任务后立即返回
        """
        logger.info("🚀 启动单次任务模式（适配GitHub Actions）")
        self.run(test_mode=test_mode)
        logger.info("📤 单次任务执行完毕，进程将退出")

def main():
    """主函数 - 根据环境变量决定运行模式"""
    # 验证配置
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        logger.info("请检查环境变量是否配置正确")
        return

    # 创建实例
    digest = ArxivDailyDigest()

    # 判断运行模式
    # 如果在GitHub Actions中，使用单次运行模式
    # 可以通过环境变量 RUN_IN_CI 或直接判断 GITHUB_ACTIONS 环境变量
    if os.getenv('GITHUB_ACTIONS') == 'true' or os.getenv('RUN_MODE') == 'ci':
        logger.info("检测到CI/CD环境，使用单次运行模式")
        # 在GitHub Actions中，TEST_MODE应该为False
        digest.run_once(test_mode=False)
    else:
        # 本地环境：根据配置决定运行模式
        if Config.TEST_MODE:
            logger.info("运行本地测试模式...")
            digest.run(test_mode=True)
        else:
            # 本地定时模式 - 如果需要的话
            # 注意：这里需要导入schedule库，但为了清晰我建议创建另一个文件
            logger.info("本地环境请使用原来的定时运行模式")
            logger.info("提示：请运行原来的版本或创建新的本地运行脚本")
            # 或者可以选择直接运行一次
            logger.info("本次直接运行一次任务...")
            digest.run_once(test_mode=False)

if __name__ == "__main__":
    main()
