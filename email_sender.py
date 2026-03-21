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
            subject = f"Arxiv原子-微腔论文摘要 - {current_date}"
            
            if papers:
                # 有论文的情况
                html_content = self._build_html_content(papers, summaries)
                text_content = self._build_text_content(papers, summaries)
                log_msg = f"发送 {len(papers)} 篇论文摘要"
            else:
                # 没有论文的情况
                html_content = self._build_no_papers_html()
                text_content = self._build_no_papers_text()
                log_msg = "发送『今日无新论文』通知"
            
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
                    <p>Arxiv 原子-微腔论文监控报告</p>
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
        ARXIV 原子-微腔论文监控报告
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
    
    def _build_text_content(self, papers, summaries):
        """构建纯文本内容"""
        content = [
            f"Arxiv 原子-微腔论文每日摘要",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"共发现 {len(papers)} 篇相关论文",
            "=" * 60,
            ""
        ]
        
        for i, (paper, summary) in enumerate(zip(papers, summaries), 1):
            content.append(f"论文 #{i}: {paper['title']}")
            content.append(summary)
            
        return "\n".join(content)
    
    def _build_html_content(self, papers, summaries):
        """构建HTML内容"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .paper {{ margin: 20px 0; padding: 15px; border: 1px solid #e0e0e0; border-radius: 5px; }}
                .title {{ color: #2c3e50; font-size: 18px; margin-bottom: 10px; }}
                .meta {{ color: #7f8c8d; font-size: 14px; margin-bottom: 10px; }}
                .abstract {{ background: #f9f9f9; padding: 10px; border-radius: 3px; }}
                .links {{ margin-top: 10px; }}
                .link {{ color: #3498db; text-decoration: none; margin-right: 15px; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📚 Arxiv 原子-微腔论文每日摘要</h1>
                <p>日期: {datetime.now().strftime('%Y年%m月%d日')} | 共 {len(papers)} 篇论文</p>
            </div>
        """
        
        for i, (paper, summary) in enumerate(zip(papers, summaries), 1):
            html += f"""
            <div class="paper">
                <div class="title">📄 论文 #{i}: {paper['title']}</div>
                <div class="meta">
                    👥 作者: {', '.join(paper['authors'][:3])}{'等' if len(paper['authors']) > 3 else ''}<br>
                    📅 发布时间: {paper['published']} | 📚 分类: {paper['primary_category']}
                </div>
                <div class="abstract">
                    <strong>摘要:</strong><br>
                    {paper['abstract'][:500]}...
                </div>
                <div class="links">
                    <a class="link" href="{paper['pdf_url']}">📥 下载PDF</a>
                    <a class="link" href="{paper['arxiv_url']}">🔗 查看原文</a>
                </div>
            </div>
            """
        
        html += """
            <hr>
            <p style="color: #95a5a6; font-size: 12px;">
                此邮件由Arxiv自动摘要系统生成 | 关键词: 原子-微腔, Rydberg atom
            </p>
        </body>
        </html>
        """
        return html
    
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
