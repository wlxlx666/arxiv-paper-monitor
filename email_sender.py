import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from config import Config

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self):
        self.sender = Config.EMAIL_SENDER
        self.password = Config.EMAIL_PASSWORD
        self.recipient = Config.RECIPIENT_EMAIL

    def send_digest(self, papers: list, summaries: list):
        """发送每日摘要邮件（包含无论文的情况）"""
        current_date = datetime.now().strftime('%Y-%m-%d')

        try:
            subject = f"📚 Arxiv论文精选 - {current_date}"

            if papers:
                # 有论文的情况
                html_content = self._build_html_content(papers)
                text_content = self._build_text_content(papers)
                log_msg = f"发送 {len(papers)} 篇论文摘要"
            else:
                # 没有论文的情况
                html_content = self._build_no_papers_html()
                text_content = self._build_no_papers_text()
                log_msg = "发送『今日无新论文』通知"

            # 本地测试模式：不真正发信，打印内容到控制台
            if not getattr(Config, 'SEND_EMAIL', True):
                print("\n" + "=" * 20 + " 邮件主题 " + "=" * 20)
                print(subject)
                print("=" * 20 + " 纯文本版本 " + "=" * 20)
                print(text_content)
                print("=" * 20 + " HTML 版本 " + "=" * 20)
                print(html_content)
                print("=" * 56 + "\n")
                logger.info(f"[本地测试] 已打印邮件内容（SEND_EMAIL=false），不实际发送 → {self.recipient}")
                return True

            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender
            msg['To'] = self.recipient

            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))

            # 发送邮件
            self._send_email(msg)
            logger.info(f"✅ {log_msg} → {self.recipient}")
            return True

        except Exception as e:
            logger.error(f"❌ haha: {e}")
            return False

    def _build_no_papers_html(self):
        """构建『无论文』的HTML邮件内容"""
        current_date = datetime.now().strftime('%Y年%m月%d日')
        keywords = ', '.join(Config.SEARCH_KEYWORDS)

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center; }}
                .icon {{ font-size: 48px; margin: 20px 0; }}
                .content {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin: 20px 0; }}
                .search-info {{ background: #e8f4fd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ color: #6c757d; font-size: 12px; text-align: center; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="icon">📭</div>
                    <h1 style="color: #6c757d;">今日无新论文</h1>
                    <p>Arxiv 论文监控报告</p>
                </div>

                <div class="content">
                    <h2>📅 报告日期：{current_date}</h2>

                    <div class="search-info">
                        <h3>🔍 搜索条件</h3>
                        <p><strong>关键词：</strong>{keywords}</p>
                        <p><strong>时间范围：</strong>最近24小时</p>
                        <p><strong>数据库：</strong>arXiv.org</p>
                    </div>

                    <h3>✅ 系统运行正常</h3>
                    <p>监控系统已成功运行，但在过去24小时内未发现符合条件的新论文。</p>

                    <h3>可能的原因：</h3>
                    <ul>
                        <li>相关领域今日确实无新论文发表</li>
                        <li>论文发布时间在今日9点之后（下次检查可见）</li>
                        <li>部分论文可能使用不同关键词</li>
                    </ul>

                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p><strong>💡 建议：</strong>如需调整搜索条件，请修改配置文件中的关键词设置。</p>
                    </div>
                </div>

                <div class="footer">
                    <p>此邮件由 Arxiv 自动监控系统生成</p>
                    <p>下次报告时间：明日 09:00</p>
                </div>
            </div>
        </body>
        </html>
        """

    def _build_no_papers_text(self):
        """构建『无论文』的纯文本邮件内容"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        keywords = ', '.join(Config.SEARCH_KEYWORDS)

        return f"""
        {'='*60}
        ARXIV 论文监控报告
        {'='*60}

        报告日期：{current_date}
        状态：今日无新论文

        📊 监控摘要：
        • 系统已成功运行
        • 搜索时间：最近24小时
        • 关键词：{keywords}
        • 结果：未发现符合条件的新论文

        🔍 可能原因：
        1. 相关领域今日确实无新论文发表
        2. 论文发布时间在今日9点之后
        3. 论文使用了不同的关键词

        💡 建议：
        如需调整搜索条件，请修改配置文件中的关键词。

        {'='*60}
        此报告由 Arxiv 自动监控系统生成
        下次报告：明日 09:00
        {'='*60}
        """

    def _build_text_content(self, papers):
        """构建纯文本内容（分区块）"""
        top_papers = [p for p in papers if p.get('is_top')]
        other_papers = [p for p in papers if not p.get('is_top')]

        content = [
            f"Arxiv 论文每日摘要",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"共发现 {len(papers)} 篇相关论文",
            "=" * 60,
            "",
        ]

        if top_papers:
            content.append("📌 今日最值得读")
            content.append("-" * 40)
            for p in top_papers:
                content.append(self._paper_text_block(p))
        if other_papers:
            content.append("📚 其他论文")
            content.append("-" * 40)
            for p in other_papers:
                content.append(self._paper_text_block(p))

        return "\n".join(content)

    def _paper_text_block(self, paper):
        """生成单篇论文的纯文本块"""
        lines = [
            f"📄 标题: {paper['title']}",
            f"👥 作者: {', '.join(paper['authors'][:3])}{'等' if len(paper['authors']) > 3 else ''}",
            f"📅 发布时间: {paper['published']} | 📚 分类: {paper['primary_category']}",
            f"🏷️ 命中关键词: {', '.join(paper.get('matched_keywords', ['未知']))}",
        ]
        if paper.get('reason'):
            lines.append(f"💡 AI 相关度: {paper['reason']} (重要性 {paper.get('importance', '?')}/5)")
        lines.extend(self._author_profile_text(paper))
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
            lines.append(paper['abstract'][:500] + ("..." if len(paper['abstract']) > 500 else ""))
            if paper.get('full_text_read'):
                lines.append("")
                lines.append("⚠️ AI 总结失败，以上为原文摘要")
        lines.append("")
        lines.append(f"🔗 PDF: {paper['pdf_url']}")
        lines.append(f"🔗 Arxiv: {paper['arxiv_url']}")
        lines.append("-" * 40)
        return "\n".join(lines)

    def _build_html_content(self, papers):
        """构建分区块HTML内容：今日最值得读 + 其他论文"""
        top_papers = [p for p in papers if p.get('is_top')]
        other_papers = [p for p in papers if not p.get('is_top')]

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; text-align: center; }}
                .section-title {{ margin: 25px 0 10px; padding: 10px 15px; border-radius: 5px; }}
                .paper {{ margin: 20px 0; padding: 15px; border: 1px solid #e0e0e0; border-radius: 5px; }}
                .top-paper {{ border: 2px solid #e74c3c; background: #fff9f9; }}
                .title {{ color: #2c3e50; font-size: 18px; margin-bottom: 10px; }}
                .meta {{ color: #7f8c8d; font-size: 13px; margin-bottom: 10px; }}
                .reason {{ color: #2980b9; font-size: 14px; margin-bottom: 8px; }}
                .ai-summary {{ background: #f0f8ff; padding: 10px; border-radius: 3px; margin: 8px 0; }}
                .highlights {{ background: #fffbe6; padding: 10px; border-radius: 3px; margin: 8px 0; }}
                .abstract {{ background: #f9f9f9; padding: 10px; border-radius: 3px; }}
                .links {{ margin-top: 10px; }}
                .link {{ color: #3498db; text-decoration: none; margin-right: 15px; }}
                .kw {{ color: #e74c3c; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📚 Arxiv 论文精选</h1>
                    <p>日期: {datetime.now().strftime('%Y年%m月%d日')} | 共 {len(papers)} 篇论文</p>
                </div>
        """

        if top_papers:
            html += """
                <div class="section-title" style="background:#e74c3c;color:white;font-size:18px;">
                    📌 今日最值得读
                </div>
            """
            for p in top_papers:
                html += self._paper_html_block(p, top=True)

        if other_papers:
            html += """
                <div class="section-title" style="background:#34495e;color:white;font-size:18px;">
                    📚 其他论文
                </div>
            """
            for p in other_papers:
                html += self._paper_html_block(p, top=False)

        html += """
                <hr>
                <p style="color: #95a5a6; font-size: 12px; text-align: center;">
                    此邮件由Arxiv自动摘要系统生成 | AI精读: DeepSeek
                </p>
            </div>
        </body>
        </html>
        """
        return html

    def _author_profile_text(self, paper):
        """纯文本版作者画像区块"""
        ap = paper.get('author_profiles')
        if not ap:
            return []

        def rep_line(name):
            rep = (ap.get('representative_works') or {}).get(name)
            if rep and rep.get('title'):
                year = rep.get('year') or '?'
                cite = f", 引用{rep['citation_count']}" if rep.get('citation_count') else ''
                src = "SS" if rep.get('source') == 'semantic_scholar' else "arXiv"
                return f"{name} -> {rep['title']} ({year}{cite}) [{src}]"
            return f"{name} -> 未找到代表作"

        lines = []
        if ap.get('first_affiliation'):
            lines.append(f"🏛️ 第一单位: {ap['first_affiliation']}")
        if ap.get('first_author'):
            lines.append(f"🧑‍🔬 第一作者: {rep_line(ap['first_author'])}")
        for a in ap.get('co_first_authors', [])[:3]:
            lines.append(f"🤝 共同一作: {rep_line(a)}")
        for a in ap.get('corresponding', [])[:3]:
            lines.append(f"📧 通讯作者: {rep_line(a)}")
        return lines

    def _paper_html_block(self, paper, top=False):
        """生成单篇论文的HTML卡片"""
        cls = 'top-paper' if top else 'paper'
        keywords_str = ', '.join(paper.get('matched_keywords', ['未知']))

        block = f"""
            <div class="{cls}">
                <div class="title">📄 {paper['title']}</div>
                <div class="meta">
                    👥 作者: {', '.join(paper['authors'][:3])}{'等' if len(paper['authors']) > 3 else ''}<br>
                    📅 发布时间: {paper['published']} | 📚 分类: {paper['primary_category']}<br>
                    🏷️ <strong>命中关键词:</strong> <span class="kw">{keywords_str}</span>
                </div>
        """
        if paper.get('reason'):
            block += f"""
                <div class="reason">💡 <strong>AI 相关度:</strong> {paper['reason']} <span style="color:#e74c3c;">(重要性 {paper.get('importance', '?')}/5)</span></div>
            """
        block += self._author_profile_html(paper)
        if paper.get('ai_summary'):
            block += f"""
                <div class="ai-summary">
                    <strong>🤖 AI 中文总结:</strong><br>
                    {paper['ai_summary']}
                </div>
            """
            if paper.get('highlights'):
                block += """
                    <div class="highlights">
                        <strong>✨ 亮点:</strong><br>
                """
                for h in paper['highlights']:
                    block += f"• {h}<br>"
                block += "</div>"
        else:
            abstract = paper['abstract'][:500] + ("..." if len(paper['abstract']) > 500 else "")
            block += f"""
                <div class="abstract">
                    <strong>📝 摘要:</strong><br>
                    {abstract}
                </div>
            """
            if paper.get('full_text_read'):
                block += '<p style="color:#e67e22;font-size:13px;">⚠️ AI 总结失败，以上为原文摘要</p>'
        block += f"""
                <div class="links">
                    <a class="link" href="{paper['pdf_url']}">📥 下载PDF</a>
                    <a class="link" href="{paper['arxiv_url']}">🔗 查看原文</a>
                </div>
            </div>
        """
        return block

    def _author_profile_html(self, paper):
        """生成作者画像区块：第一单位 + 关键作者代表作"""
        ap = paper.get('author_profiles')
        if not ap:
            return ''
        rows = []

        def rep_line(name):
            rep = (ap.get('representative_works') or {}).get(name)
            if rep and rep.get('title'):
                year = rep.get('year') or '?'
                cite = f", 引用{rep['citation_count']}" if rep.get('citation_count') else ''
                src = "SS" if rep.get('source') == 'semantic_scholar' else "arXiv"
                return f"{name} → <em>{rep['title']}</em> ({year}{cite}) <span style='color:#95a5a6'>[{src}]</span>"
            return f"{name} → <span style='color:#95a5a6'>未找到代表作</span>"

        if ap.get('first_affiliation'):
            rows.append(f"🏛️ <strong>第一单位:</strong> {ap['first_affiliation']}")
        if ap.get('first_author'):
            rows.append("🧑‍🔬 <strong>第一作者:</strong> " + rep_line(ap['first_author']))
        for a in ap.get('co_first_authors', [])[:3]:
            rows.append("🤝 <strong>共同一作:</strong> " + rep_line(a))
        for a in ap.get('corresponding', [])[:3]:
            rows.append("📧 <strong>通讯作者:</strong> " + rep_line(a))
        if not rows:
            return ''

        body = "<br>".join(rows)
        return f"""
            <div style="background:#f3f6fa; padding:10px; border-radius:3px; margin:8px 0; font-size:14px; line-height:1.7;">
                {body}
            </div>
        """

    def _send_email(self, msg):
        """修复：忽略SSL关闭错误，正确返回发送成功"""
        sender = self.sender
        password = self.password

        try:
            if "qq.com" in sender:
                # 使用TLS连接
                with smtplib.SMTP('smtp.qq.com', 587, timeout=30) as server:
                    server.starttls()
                    server.login(sender, password)
                    server.send_message(msg)  # 邮件发送核心步骤

                    # 邮件发送成功后，忽略关闭连接时的错误
                    try:
                        server.quit()
                    except:
                        pass  # 忽略所有退出错误

            elif "163.com" in sender:
                with smtplib.SMTP('smtp.163.com', 587, timeout=30) as server:
                    server.starttls()
                    server.login(sender, password)
                    server.send_message(msg)
                    try:
                        server.quit()
                    except:
                        pass

            else:
                with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=30) as server:
                    server.login(sender, password)
                    server.send_message(msg)
                    try:
                        server.quit()
                    except:
                        pass

        except Exception as e:
            error_msg = str(e)

            # 关键：如果是SSL关闭错误，不抛出异常（邮件已发送成功）
            if "(-1, b'\\x00\\x00\\x00')" in error_msg:
                print("✅ 邮件已发送成功（忽略SSL关闭错误）")
                return  # 正常返回，不抛出异常
            else:
                # 其他错误才真正抛出
                print(f"❌ 真正的发送失败: {e}")
                raise
            raise
