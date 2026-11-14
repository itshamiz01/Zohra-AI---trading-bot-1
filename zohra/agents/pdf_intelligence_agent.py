"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — PDF INTELLIGENCE AGENT                     ║
║            Dynamic PDF Text Extraction & Section Parsing             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import logging
from typing import Dict, List, Any

logger = logging.getLogger("zohra.research.pdf")

class PDFIntelligenceAgent:
    """
    Parses PDF documents, extracts text content page-by-page, and segments
    it into sections (Abstract, Methodology, Results) for analysis.
    """
    def extract_text(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
            
        text_content = []
        num_pages = 0
        
        # 1. Try importing pypdf
        try:
            import pypdf
            logger.info(f"Using pypdf to parse {file_path}")
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)
                for i in range(num_pages):
                    page_text = reader.pages[i].extract_text() or ""
                    text_content.append(page_text)
        except ImportError:
            # 2. Try importing pdfplumber
            try:
                import pdfplumber
                logger.info(f"Using pdfplumber to parse {file_path}")
                with pdfplumber.open(file_path) as pdf:
                    num_pages = len(pdf.pages)
                    for page in pdf.pages:
                        page_text = page.extract_text() or ""
                        text_content.append(page_text)
            except ImportError:
                # 3. Fallback: return message if no libraries are available
                logger.warning("No PDF parsing libraries (pypdf, pdfplumber) found. Cannot extract text.")
                return {
                    "error": "PDF parsing libraries not installed. Please install pypdf or pdfplumber.",
                    "file_name": os.path.basename(file_path),
                    "file_size": os.path.getsize(file_path)
                }

        full_text = "\n".join(text_content)
        sections = self._parse_sections(full_text)
        
        return {
            "file_name": os.path.basename(file_path),
            "num_pages": num_pages,
            "full_text": full_text[:50000], # Cap to avoid token bloat
            "sections": sections
        }

    def _parse_sections(self, text: str) -> Dict[str, str]:
        """Attempts to segment the text into standard scientific sections."""
        sections = {"abstract": "", "methodology": "", "conclusion": "", "other": ""}
        text_lower = text.lower()
        
        # Simple keyword boundaries
        abs_idx = text_lower.find("abstract")
        intro_idx = text_lower.find("introduction")
        method_idx = text_lower.find("methodology")
        if method_idx == -1:
            method_idx = text_lower.find("methods")
        conc_idx = text_lower.find("conclusion")
        if conc_idx == -1:
            conc_idx = text_lower.find("concluding remarks")
            
        if abs_idx != -1:
            end = intro_idx if intro_idx != -1 else (method_idx if method_idx != -1 else len(text))
            sections["abstract"] = text[abs_idx:end].strip()
            
        if method_idx != -1:
            end = conc_idx if conc_idx != -1 else len(text)
            sections["methodology"] = text[method_idx:end].strip()
            
        if conc_idx != -1:
            sections["conclusion"] = text[conc_idx:].strip()
            
        return sections

# Singleton
pdf_intelligence_agent = PDFIntelligenceAgent()
