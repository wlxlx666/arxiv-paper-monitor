import json
import logging
import re
import time

import requests
from llm_summarizer import LLMSummarizer
from config import Config

logger = logging.getLogger(__name__)

_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_ARXIV_API = "https://export.arxiv.org/api/query"


class AuthorProfiles:
    """解析论文作者角色/第一单位，并查找作者代表作"""

    def __init__(self):
        self.llm = LLMSummarizer()
        self._rep_cache = {}
        self.timeout = getattr(Config, 'SEMANTIC_SCHOLAR_TIMEOUT', 10)
        self.max_authors = getattr(Config, 'MAX_AUTHOR_PROFILES', 5)

    def parse_authors(self, paper: dict, full_text: str = None) -> dict:
        """用 DeepSeek 从 PDF 首页解析第一作者/共同一作/通讯作者/第一单位"""
        source_text = full_text or paper.get('abstract', '')
        head = source_text[:3000]
        if len(head) < 100:
            return self._fallback_parse(paper)
        system_prompt = (
            "你是一名学术文献助手。给定一篇论文的首页文本（含标题、作者列表、单位列表、通讯标注）。"
            "请解析并只返回 JSON，格式："
            "{\"first_author\": \"姓名\", \"co_first_authors\": [\"姓名\", ...], "
            "\"corresponding\": [\"姓名\", ...], \"first_affiliation\": \"第一作者所属单位\"}"
            "规则：第一作者是作者列表第一个；共同一作通常是标有相同上标数字或作者的脚注/等号标注；"
            "通讯作者通常带*或corresponding标注；first_affiliation 取第一作者上标数字对应的单位。"
            "无法确定时用空字符串或空数组。不要编造姓名。"
        )
        user_prompt = json.dumps({
            "title": paper.get('title', ''),
            "arxiv_authors": paper.get('authors', [])[:20],
            "text_head": head,
        }, ensure_ascii=False)
        data = self.llm._chat_json(system_prompt, user_prompt)
        if not data:
            return self._fallback_parse(paper)
        first = str(data.get('first_author', '') or '').strip()
        co_first = [str(a).strip() for a in data.get('co_first_authors', []) if str(a).strip()]
        corr = [str(a).strip() for a in data.get('corresponding', []) if str(a).strip()]
        affil = str(data.get('first_affiliation', '') or '').strip()
        # 净化姓名（去掉上标编号）
        clean = lambda n: re.sub(r'[0-9*†‡#\s]+$', '', n).strip()
        if first:
            first = clean(first)
        co_first = [clean(n) for n in co_first if clean(n)]
        corr = [clean(n) for n in corr if clean(n)]
        if not first and not corr:
            return self._fallback_parse(paper)
        return {
            'first_author': first,
            'co_first_authors': co_first,
            'corresponding': corr,
            'first_affiliation': affil,
        }

    def _fallback_parse(self, paper: dict) -> dict:
        """无 key 或解析失败时：arXiv 作者列表第一人作为第一作者"""
        authors = paper.get('authors', [])
        return {
            'first_author': authors[0] if authors else '',
            'co_first_authors': [],
            'corresponding': [],
            'first_affiliation': '',
        }

    def find_representative_work(self, author_name: str) -> dict:
        """查作者代表作：Semantic Scholar 优先，arXiv 兜底。带缓存"""
        if not author_name:
            return None
        name = author_name.strip()
        if name in self._rep_cache:
            return self._rep_cache[name]
        result = self._ss_representative(name) or self._arxiv_representative(name)
        if result:
            self._rep_cache[name] = result
        return result

    def _ss_representative(self, name: str) -> dict:
        """用 Semantic Scholar 查引用数最高的代表作"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 arxiv-digest/1.0'}
            # 1. 搜作者，取 paperCount 最大的
            r = requests.get(
                f"{_SS_BASE}/author/search",
                params={'query': name, 'fields': 'name,paperCount'},
                headers=headers,
                timeout=self.timeout,
            )
            if r.status_code != 200:
                if r.status_code == 429:
                    time.sleep(2)
                    r = requests.get(
                        f"{_SS_BASE}/author/search",
                        params={'query': name, 'fields': 'name,paperCount'},
                        headers=headers,
                        timeout=self.timeout,
                    )
                if r.status_code != 200:
                    return None
            authors = r.json().get('data', [])
            if not authors:
                return None
            authors = sorted(authors, key=lambda a: a.get('paperCount') or 0, reverse=True)
            author_id = authors[0]['authorId']
            # 2. 查该作者论文，按引用排序取第 1
            r2 = requests.get(
                f"{_SS_BASE}/author/{author_id}/papers",
                params={'limit': 10, 'fields': 'title,year,citationCount'},
                headers=headers,
                timeout=self.timeout,
            )
            if r2.status_code != 200:
                return None
            papers = [p for p in r2.json().get('data', []) if p.get('title')]
            papers.sort(key=lambda p: p.get('citationCount') or 0, reverse=True)
            if not papers:
                return None
            top = papers[0]
            return {
                'title': top['title'],
                'year': top.get('year'),
                'citation_count': top.get('citationCount'),
                'source': 'semantic_scholar',
            }
        except Exception as e:
            logger.debug(f"Semantic Scholar 查询失败 {name}: {e}")
            return None

    def _arxiv_representative(self, name: str) -> dict:
        """arXiv 兜底：取作者最新一篇预印本"""
        try:
            r = requests.get(
                _ARXIV_API,
                params={'search_query': f'au:"{name}"', 'max_results': 1, 'sortBy': 'submittedDate', 'sortOrder': 'descending'},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return None
            import xml.etree.ElementTree as ET
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            root = ET.fromstring(r.text)
            entry = root.find('atom:entry', ns)
            if entry is None:
                return None
            title_el = entry.find('atom:title', ns)
            pub_el = entry.find('atom:published', ns)
            title = ' '.join((title_el.text or '').split())
            year = None
            if pub_el is not None and pub_el.text:
                m = re.match(r'(\d{4})', pub_el.text)
                year = int(m.group(1)) if m else None
            return {
                'title': title,
                'year': year,
                'citation_count': None,
                'source': 'arxiv',
            }
        except Exception as e:
            logger.debug(f"arXiv 兜底查询失败 {name}: {e}")
            return None

    def build_author_profiles(self, paper: dict, full_text: str = None) -> dict:
        """组合：解析作者角色 + 为关键作者查代表作"""
        roles = self.parse_authors(paper, full_text)
        first_affiliation = roles.get('first_affiliation', '')

        # 收集需要查代表作的关键作者（去重，限数量）
        author_names = []
        for a in [roles.get('first_author', '')] + roles.get('co_first_authors', []) + roles.get('corresponding', []):
            if a and a not in author_names:
                author_names.append(a)
        author_names = author_names[:self.max_authors]

        profiles = {}
        for a in author_names:
            rep = self.find_representative_work(a)
            profiles[a] = rep or {'title': None, 'year': None, 'citation_count': None, 'source': None}

        return {
            'first_author': roles.get('first_author', ''),
            'co_first_authors': roles.get('co_first_authors', []),
            'corresponding': roles.get('corresponding', []),
            'first_affiliation': first_affiliation,
            'representative_works': profiles,
        }
