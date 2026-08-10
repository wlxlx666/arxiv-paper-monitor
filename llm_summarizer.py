import json
import logging
import time

from config import Config

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class LLMSummarizer:
    """调用 DeepSeek 对论文进行打分、排序和精读总结"""

    MAX_FULL_TEXT_CHARS = 12000

    def __init__(self):
        self.api_key = getattr(Config, 'DEEPSEEK_API_KEY', None)
        self.model = getattr(Config, 'DEEPSEEK_MODEL', 'deepseek-chat')
        self.enabled = bool(self.api_key) and OpenAI is not None

    def _client(self):
        return OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")

    def _chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        """调用 DeepSeek，要求返回 JSON，失败重试 2 次"""
        if not self.enabled:
            return None
        for attempt in range(3):
            try:
                client = self._client()
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    max_tokens=3000,
                )
                content = resp.choices[0].message.content
                return json.loads(content)
            except Exception as e:
                logger.warning(f"DeepSeek 调用失败（第{attempt + 1}次）: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt * 2)
        return None

    def score_papers(self, papers: list) -> dict:
        """批量给所有论文打分（仅读标题+摘要），返回 {index: {'importance': 1-5, 'reason': 中文一句}}"""
        if not self.enabled or not papers:
            return {}
        items = [
            {
                "index": i,
                "title": p['title'],
                "abstract": p['abstract'][:800],
                "categories": p.get('primary_category', ''),
            }
            for i, p in enumerate(papers)
        ]
        system_prompt = (
            "你是一名物理与量子信息领域的文献筛选助手。"
            "用户关心关键词如里德堡原子、光镊阵列、集成光子学、腔量子电动力学、纳米光纤、FPGA等。"
            "请为每篇论文按与用户研究兴趣的相关性打分 importance(1-5)，并给出一句中文相关度理由 reason。"
            "只返回 JSON，格式：{\"scores\": [{\"index\": 0, \"importance\": 4, \"reason\": \"...\"}, ...]}"
        )
        user_prompt = json.dumps(items, ensure_ascii=False)
        data = self._chat_json(system_prompt, user_prompt)
        if not data or "scores" not in data:
            return {}
        scores = {}
        for s in data["scores"]:
            try:
                idx = int(s["index"])
                scores[idx] = {
                    "importance": int(s.get("importance", 3)),
                    "reason": str(s.get("reason", "")),
                }
            except (KeyError, ValueError, TypeError):
                continue
        return scores

    def summarize_paper(self, paper: dict, full_text: str = None) -> dict:
        """精读一篇论文，返回 {summary(中文), highlights([3-5条中文])}，失败返回 None"""
        if not self.enabled:
            return None
        content = full_text or paper.get('abstract', '')
        if full_text and len(content) > self.MAX_FULL_TEXT_CHARS:
            content = content[:self.MAX_FULL_TEXT_CHARS]
        if len(content) < 50:
            return None
        system_prompt = (
            "你是一名物理与量子信息领域的学术助手。请用中文精读给定论文内容。"
            "只返回 JSON，格式："
            "{\"summary\": \"2-4句中文，概括论文要解决的问题、方法、主要结果与意义\", "
            "\"highlights\": [\"亮点1\", \"亮点2\", ...]}"
            "要求：标题保留英文，不翻译；总结和亮点用中文；亮点3-5条，突出创新点与关键技术。"
        )
        user_prompt = json.dumps({
            "title": paper['title'],
            "authors": paper.get('authors', [])[:5],
            "published": paper.get('published', ''),
            "content": content,
        }, ensure_ascii=False)
        data = self._chat_json(system_prompt, user_prompt)
        if not data:
            return None
        return {
            "summary": str(data.get("summary", "")).strip(),
            "highlights": [str(h).strip() for h in data.get("highlights", []) if str(h).strip()],
        }

    def select_top_for_deep_read(self, scores: dict, count: int) -> list:
        """按 importance 从高到低选出 count 个索引用于精读"""
        ranked = sorted(scores.items(), key=lambda kv: kv[1]["importance"], reverse=True)
        return [idx for idx, _ in ranked[:count]]
