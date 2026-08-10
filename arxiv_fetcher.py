import arxiv
import requests
import re
from datetime import datetime
from typing import List, Dict
import logging
from config import Config

logger = logging.getLogger(__name__)

class ArxivFetcher:
    def __init__(self):
        self.client = arxiv.Client()
        self.keywords = Config.SEARCH_KEYWORDS
        
    def fetch_recent_papers(self, days_back: int = 1, max_results: int = 50, hours_back: int = None) -> List[Dict]:
        """获取符合关键词的论文"""
        try:
            from datetime import timedelta # 确保导入了 timedelta

            # 1. 基础关键词查询
            keyword_query = " OR ".join([f'all:"{kw.strip()}"' for kw in self.keywords])
            query = f"({keyword_query})"

            # === 时间限制逻辑：默认用小时，回退到天 ===
            if hours_back is not None:
                end_date = datetime.now()
                start_date = end_date - timedelta(hours=hours_back)
                date_range = f"[{start_date.strftime('%Y%m%d')} TO {end_date.strftime('%Y%m%d')}]"
                query += f" AND submittedDate:{date_range}"
                logger.info(f"搜索时间范围: 当前时间前 {hours_back} 小时")
            elif days_back > 0:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days_back)
                date_range = f"[{start_date.strftime('%Y%m%d')} TO {end_date.strftime('%Y%m%d')}]"
                query += f" AND submittedDate:{date_range}"
            
            logger.info(f"搜索查询: {query}")
            
            fetch_limit = getattr(Config, 'MAX_RESULTS', max_results)
            
            search = arxiv.Search(
                query=query,
                max_results=fetch_limit,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            # ... 下面的解析和返回逻辑保持不变 ...
            
            papers = []
            for result in self.client.results(search):
                paper = {
                    'id': result.get_short_id(),
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'abstract': result.summary,
                    'pdf_url': result.pdf_url,
                    'published': result.published.strftime('%Y-%m-%d %H:%M'),
                    'primary_category': result.primary_category,
                    'categories': result.categories,
                    'arxiv_url': result.entry_id,
                }
                
                # === 新增逻辑：提取命中的关键词 ===
                matched_kws = []
                # 将标题和摘要合并，转为小写进行无大小写敏感匹配
                search_text = (paper['title'] + " " + paper['abstract']).lower()
                for kw in self.keywords:
                    # 将关键词也转为小写进行匹配
                    if kw.strip().lower() in search_text:
                        matched_kws.append(kw.strip())
                
                # 如果因为API分词原因没有精确匹配到原词，给个默认提示
                if not matched_kws:
                    matched_kws = ["模糊匹配"]
                    
                paper['matched_keywords'] = matched_kws
                # =================================
                
                papers.append(paper)
                logger.info(f"找到论文: {paper['title'][:50]}... [关键词: {', '.join(matched_kws)}]")
            
            logger.info(f"共找到 {len(papers)} 篇相关论文")
            return papers
            
        except Exception as e:
            logger.error(f"获取论文失败: {e}", exc_info=True) # exc_info=True 有助于打印完整的错误堆栈
            return []
    
    def download_pdf(self, paper: Dict) -> bytes:
        """下载论文 PDF 文件，失败返回 None"""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
            resp = requests.get(paper['pdf_url'], headers=headers, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
            logger.warning(f"PDF 下载异常: {paper['pdf_url']} -> HTTP {resp.status_code}")
            return None
        except Exception as e:
            logger.warning(f"PDF 下载失败 {paper['pdf_url']}: {e}")
            return None

    def extract_text(self, pdf_bytes: bytes) -> str:
        """用 PyMuPDF 提取 PDF 前几页文本，失败返回 None"""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            max_pages = getattr(Config, 'PDF_PAGES', 6)
            text = []
            for page in doc:
                if len(text) >= max_pages:
                    break
                text.append(page.get_text())
            doc.close()
            full = "\n".join(text).strip()
            return full if len(full) > 100 else None
        except Exception as e:
            logger.warning(f"PDF 文本提取失败: {e}")
            return None

    def get_paper_full_text(self, paper: Dict) -> str:
        """下载并提取 PDF 全文文本，任一步失败返回 None"""
        pdf_bytes = self.download_pdf(paper)
        if pdf_bytes is None:
            return None
        return self.extract_text(pdf_bytes)

    def extract_figure1(self, paper: Dict) -> Dict:
        """提取论文图 1：定位 Fig.1 标题所在页，优先取嵌入图，无则页面截图。
        返回 {content: PNG bytes, caption: 图题文本}，失败返回 None"""
        if not getattr(Config, 'EXTRACT_FIGURE1', True):
            return None
        try:
            import io
            import fitz  # PyMuPDF
            pdf_bytes = self.download_pdf(paper)
            if pdf_bytes is None:
                return None
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            fig_pat = re.compile(r'(?i)fig(?:ure)?\.?\s*1\s*[\.:\-]')

            for pno in range(doc.page_count):
                page = doc[pno]
                text = page.get_text('text')
                m = fig_pat.search(text)
                if not m:
                    continue
                # 提取图题：从 Fig.1 标题行起，到下一个 Figure 标题或页末
                caption = self._extract_caption(text, m.end())
                content = None
                # 优先：该页第一张嵌入图
                imgs = page.get_images(full=True)
                if imgs:
                    xref = imgs[0][0]
                    info = doc.extract_image(xref)
                    content = info['image']
                    content = self._to_png(content, info['ext'])
                if content is None:
                    # 兜底：截图页面 caption 上方区域（覆盖矢量图）
                    rl = page.search_for(m.group(0))
                    cap_y = rl[0].y0 if rl else page.rect.height
                    clip = fitz.Rect(0, 0, page.rect.width, max(cap_y - 10, 10))
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=clip)
                    content = pix.tobytes("png")
                content = self._compress_image(content)
                if content:
                    doc.close()
                    return {'content': content, 'caption': caption}
            doc.close()
            return None
        except Exception as e:
            logger.warning(f"图1提取失败 {paper.get('pdf_url', '')}: {e}")
            return None

    def _extract_caption(self, text: str, start: int) -> str:
        """从 Fig.1 标题后截取图题文本（到下一个 Figure 标题或换行段落）"""
        rest = text[start:]
        # 截到下一个 Figure/Fig 标题（若存在）
        m = re.search(r'(?i)fig(?:ure)?\.?\s*\d+', rest)
        if m:
            rest = rest[:m.start()]
        lines = [ln.strip() for ln in rest.split('\n') if ln.strip()]
        cap = ' '.join(lines)[:300].strip()
        return cap

    def _to_png(self, content: bytes, ext: str) -> bytes:
        """把图片统一转为 PNG（若已是 PNG 直接返回）"""
        try:
            from PIL import Image
            import io
            if ext.lower() == 'png':
                return content
            img = Image.open(io.BytesIO(content))
            buf = io.BytesIO()
            img.convert('RGB').save(buf, format='PNG')
            return buf.getvalue()
        except Exception:
            return None

    def _compress_image(self, content: bytes) -> bytes:
        """用 PIL 压缩图片：宽度不超过 FIGURE_MAX_WIDTH，体积尽量 < 400KB"""
        try:
            from PIL import Image
            import io
            max_w = getattr(Config, 'FIGURE_MAX_WIDTH', 800)
            img = Image.open(io.BytesIO(content))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            quality = 82
            img.save(buf, format='JPEG', quality=quality)
            if buf.tell() > 400 * 1024:
                img.save(buf := io.BytesIO(), format='JPEG', quality=60)
            return buf.getvalue()
        except Exception:
            return content

    def generate_summary(self, paper: Dict) -> str:
        """生成论文的简要摘要"""
        title = paper['title']
        abstract = paper['abstract']
        
        # 简单总结逻辑
        summary_lines = [
            "=" * 60,
            f"📄 标题: {title}",
            "",
            f"👥 作者: {', '.join(paper['authors'][:3])}{' 等' if len(paper['authors']) > 3 else ''}",
            f"📅 发布时间: {paper['published']}",
            f"📚 分类: {paper['primary_category']}",
            # === 新增这一行 ===
            f"🏷️ 命中关键词: {', '.join(paper.get('matched_keywords', ['未知']))}", 
            "",
            "📝 摘要:",
            self._truncate_text(abstract, 800) + ("..." if len(abstract) > 800 else ""),
            "",
            "🔗 链接:",
            f"PDF: {paper['pdf_url']}",
            f"Arxiv: {paper['arxiv_url']}",
            "=" * 60,
            ""
        ]
        
        return "\n".join(summary_lines)
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """截断过长的文本，尽量在单词边界处截断"""
        # 移除换行符，使摘要更紧凑
        text = text.replace('\n', ' ') 
        
        if len(text) <= max_length:
            return text
            
        # 寻找在 max_length 之前的最后一个空格进行截断
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > 0:
            return truncated[:last_space]
        return truncated # 如果找不到空格，就直接硬截断
