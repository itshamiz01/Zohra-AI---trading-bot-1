"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — RESEARCH REPORT GENERATOR                  ║
║         Publication-Quality Markdown Intelligence Reports            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger("zohra.research.report")

class ReportGenerator:
    """
    Compiles raw research findings, verified claims, and citations into
    a clean, structured, and publication-ready Markdown report.
    """
    def generate_report(self, topic: str, sources: List[Dict[str, Any]], 
                        claims: List[Dict[str, Any]], project_id: str) -> str:
        lines = []
        
        # 1. Header
        lines.append(f"# ZOHRA OS — RESEARCH REPORT")
        lines.append(f"**Topic**: {topic.upper()}")
        lines.append(f"**Project ID**: `{project_id}`")
        lines.append(f"**Date**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append(f"**Publisher**: Zohra AI Research Division")
        lines.append("\n---\n")
        
        # 2. Executive Summary
        lines.append("## 1. Executive Summary")
        summary_text = (
            f"This intelligence report provides a comprehensive analysis of **{topic}**. "
            f"Zohra's Research Division crawled academic journals, web databases, and historical archives, "
            f"extracting and verifying key claims to construct a structured knowledge base."
        )
        lines.append(summary_text)
        lines.append("\n")
        
        # 3. Verified Claims
        lines.append("## 2. Verified Intelligence & Findings")
        if claims:
            for idx, c in enumerate(claims):
                status_emoji = "✅" if c["status"] == "VERIFIED" else "⚠️" if c["status"] == "PARTIALLY_VERIFIED" else "❌"
                lines.append(f"{idx+1}. **{c['claim']}**")
                lines.append(f"   - **Status**: {status_emoji} {c['status']}")
                lines.append(f"   - **Confidence**: `{c['confidence']*100:.0f}%`")
                if c["supporting_sources"]:
                    lines.append(f"   - **Sources**: {', '.join(c['supporting_sources'])}")
                lines.append("")
        else:
            lines.append("No specific claims were verified in this research cycle.")
        lines.append("\n")
        
        # 4. Source Library & Citations
        lines.append("## 3. Reference Library & Citations")
        if sources:
            for idx, src in enumerate(sources):
                title = src.get("title", "Untitled Source")
                url = src.get("url") or src.get("pdf_url", "#")
                author_list = src.get("authors")
                authors = ", ".join(author_list) if isinstance(author_list, list) else src.get("author", "Unknown Author")
                db_source = src.get("source", "Web Resource")
                
                lines.append(f"- **[{idx+1}]** [{title}]({url})")
                lines.append(f"  - *Author(s)*: {authors}")
                lines.append(f"  - *Database*: {db_source}")
        else:
            lines.append("No external sources were cited.")
            
        return "\n".join(lines)

# Singleton
report_generator = ReportGenerator()
