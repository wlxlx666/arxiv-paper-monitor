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
        """提取论文图 1：定位图1标题所在页，按布局类型选择提取策略。
        返回 {content: bytes, caption: 图题文本}，失败返回 None"""
        if not getattr(Config, 'EXTRACT_FIGURE1', True):
            return None
        try:
            import io
            import fitz  # PyMuPDF
            pdf_bytes = self.download_pdf(paper)
            if pdf_bytes is None:
                return None
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            # 宽正则：匹配 "Fig. 1"、"Figure 1"、"Fig. 1a/1b"、"Fig. 1 Schematic" 等
            # "1" 后不能跟数字（排除 Fig. 10/11/12）。正文引用页通过"嵌入图在caption上方"过滤
            fig_pat = re.compile(r'(?i)fig(?:ure)?\.?\s*1(?![0-9])')

            # 用文本块精确定位图题：遍历每页所有 "Fig. 1" 匹配，找到
            # "caption 上方有嵌入图"的位置（图实际所在处）。用 text 字符索引
            # 匹配文本块，避免 search_for 无法区分同串实例的问题。
            candidates = []
            for pno in range(doc.page_count):
                page = doc[pno]
                text = page.get_text('text')
                for m in fig_pat.finditer(text):
                    block_info = self._locate_text_block(page, m.start())
                    if not block_info:
                        continue
                    cap_y = block_info[1]  # 块顶部 y 坐标
                    has_img_above = self._has_image_above_caption(page, cap_y)
                    if has_img_above:
                        # 找到真正的图位置（caption 上方有嵌入图）
                        candidates = [(True, pno, m, cap_y)]
                        break
                if candidates:
                    break

            if not candidates:
                # 无任何位置 caption 上方有嵌入图（纯矢量图论文），
                # 回退到每个 Fig.1 匹配中"caption 上方区域较大"的第一个
                for pno in range(doc.page_count):
                    page = doc[pno]
                    text = page.get_text('text')
                    for m in fig_pat.finditer(text):
                        block_info = self._locate_text_block(page, m.start())
                        if not block_info:
                            continue
                        cap_y = block_info[1]
                        if cap_y > 0.3 * page.rect.height:  # 区域足够大
                            candidates = [(False, pno, m, cap_y)]
                            break
                    if candidates:
                        break

            if not candidates:
                doc.close()
                return None

            has_img_above, pno, m, cap_y = candidates[0]
            page = doc[pno]
            text = page.get_text('text')

            content = None
            if has_img_above:
                # 方案A：嵌入图显示矩形并集圈定图1区域（嵌入图是主体的常规布局）
                rects_union, coverage = self._figure_region(page, cap_y)
                if rects_union is not None and coverage >= 0.2:
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=rects_union)
                    content = self._sanity_check_figure(pix.tobytes("png"))
                if content is None:
                    # 方案B：嵌入图占比低（矢量图为主，如 C2C 架构图），截图 caption 上方整块
                    content = self._screenshot_above_caption(page, cap_y)
                if content is None:
                    # 方案C：取该页面积最大的嵌入图（单张独立图1）
                    best = None
                    best_area = 0
                    for img in page.get_images(full=True):
                        try:
                            area = img[2] * img[3]
                            if area > best_area:
                                best_area = area
                                best = img
                        except (IndexError, TypeError):
                            continue
                    if best is not None:
                        info = doc.extract_image(best[0])
                        content = self._to_png(info['image'], info['ext'])
                        content = self._sanity_check_figure(content)
            else:
                # 无嵌入图在 caption 上方（纯矢量图论文）：截图 caption 上方区域
                content = self._screenshot_above_caption(page, cap_y)

            content = self._compress_image(content)
            if content:
                caption = self._extract_caption(text, m.end())
                doc.close()
                return {'content': content, 'caption': caption}
            doc.close()
            return None
        except Exception as e:
            logger.warning(f"图1提取失败 {paper.get('pdf_url', '')}: {e}")
            return None

    def _has_image_above_caption(self, page, cap_y) -> bool:
        """判断 caption 上方是否有嵌入图显示"""
        imgs = page.get_images(full=True)
        for img in imgs:
            try:
                rects = page.get_image_rects(img[0])
            except Exception:
                continue
            for rect in rects:
                if rect.y1 < cap_y and rect.height > 5:  # 排除 5px 以下的装饰性图
                    return True
        return False

    def _locate_text_block(self, page, char_offset):
        """根据文本流中的字符偏移定位所属文本块。
        返回 (block, block_y_top) 或 None。用 get_text('dict') 获取块/行/span 的精确坐标，
        避免 search_for 无法区分同字符串多个实例的问题"""
        try:
            d = page.get_text('dict')
            acc = 0
            for block in d.get('blocks', []):
                if block.get('type', 0) != 0:  # 0=文本，1=图片
                    continue
                for line in block.get('lines', []):
                    for span in line.get('spans', []):
                        span_len = len(span.get('text', ''))
                        if acc <= char_offset < acc + span_len:
                            y0 = span.get('bbox', [0, 0, 0, 0])[1]
                            return (block, y0)
                        acc += span_len
            return None
        except Exception:
            return None

    def _screenshot_above_caption(self, page, cap_y) -> bytes:
        """截图 caption 上方整块区域（用于矢量图为主的图1）。
        用文本块检测排除上方正文，返回 PNG bytes 或 None"""
        import fitz  # PyMuPDF
        clip_h = max(cap_y - 10, 10)
        if clip_h < 0.15 * page.rect.height:
            return None
        # 找到 caption 上方最后一个"长句正文块"的底部 y，从它下方开始截图，
        # 避免把上方正文段落也截进来
        bottom = 0
        for b in page.get_text('blocks'):
            if b[3] < cap_y:
                txt = ' '.join(b[4].split())
                if len(txt) > 60:  # 长文本 = 正文段落
                    bottom = max(bottom, b[3])
        clip = fitz.Rect(0, bottom, page.rect.width, max(cap_y - 10, bottom + 10))
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=clip)
        return pix.tobytes("png")

    def _figure_region(self, page, cap_y):
        """计算 caption 上方嵌入图显示矩形的并集，作为图1的实际区域。
        返回 (fitz.Rect, coverage) 或 (None, 0)。coverage = 嵌入图显示总面积 / caption 上方区域面积，
        用于判断图1是"嵌入图为主"（coverage 高）还是"矢量图为主"（coverage 低，需截图整个区域）"""
        import fitz  # PyMuPDF
        imgs = page.get_images(full=True)
        y_min, y_max, x_min, x_max = None, None, None, None
        disp_area = 0
        for img in imgs:
            try:
                rects = page.get_image_rects(img[0])
            except Exception:
                continue
            for rect in rects:
                if rect.y1 < cap_y:  # 只考虑 caption 上方的图
                    y_min = rect.y0 if y_min is None else min(y_min, rect.y0)
                    y_max = rect.y1 if y_max is None else max(y_max, rect.y1)
                    x_min = rect.x0 if x_min is None else min(x_min, rect.x0)
                    x_max = rect.x1 if x_max is None else max(x_max, rect.x1)
                    disp_area += rect.width * rect.height
        if y_min is None or y_max is None:
            return None, 0.0
        region_h = y_max - y_min
        # 区域过小（<40px 高）判为无效；太贴近页面底部也不合理
        if region_h < 40 or y_max > cap_y:
            return None, 0.0
        region_area = (x_max - x_min) * (y_max - y_min)
        coverage = disp_area / region_area if region_area > 0 else 0.0
        # 稍作外扩，避免裁掉图边缘
        pad = 4
        x0 = max(x_min - pad, 0)
        y0 = max(y_min - pad, 0)
        x1 = min(x_max + pad, page.rect.width)
        y1 = min(y_max + pad, cap_y)
        return fitz.Rect(x0, y0, x1, y1), coverage

    def _sanity_check_figure(self, content) -> bytes:
        """合理性检查：如果嵌入图太扁或太小（不像图1主体），返回 None 触发截图兜底"""
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(content))
            w, h = img.size
            # 太扁（宽高比 > 4:1）或面积太小（< 40000 px²）判为可疑
            if w == 0 or h == 0:
                return None
            aspect = w / h
            if aspect > 4.0 or (w * h) < 40000:
                return None
            return content
        except Exception:
            return None

    def _extract_caption(self, text: str, start: int) -> str:
        """从 Fig.1 标题后截取图题文本（到下一个 Figure 标题或换行段落）"""
        rest = text[start:]
        # 去掉开头的标点/冒号等（正则匹配后可能残留 "1." 后的字符）
        rest = re.sub(r'^[\s\.:\-\.,;]+', '', rest)
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
