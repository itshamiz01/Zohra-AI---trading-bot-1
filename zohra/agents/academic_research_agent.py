"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — ACADEMIC RESEARCH AGENT                      ║
║            Public ArXiv API Scientific Paper Crawler                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

logger = logging.getLogger("zohra.research.academic")

class AcademicResearchAgent:
    """
    Queries the public ArXiv API to fetch peer-reviewed scientific publications,
    extracting methodology, abstract, and PDF links for Zohra's research database.
    """
    def search_papers(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        papers = []
        try:
            # Clean and format query for URL
            formatted_query = urllib.parse.quote(query)
            url = f"http://export.arxiv.org/api/query?search_query=all:{formatted_query}&max_results={max_results}"
            
            logger.info(f"Querying ArXiv: {url}")
            
            # Perform HTTP request
            import ssl
            context = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers={'User-Agent': 'ZohraOS-Research-Agent/1.0'})
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                xml_data = response.read()
                
            # Parse XML response
            root = ET.fromstring(xml_data)
            
            # Namespace map for ArXiv XML
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'
            }
            
            for entry in root.findall('atom:entry', ns):
                title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
                summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
                published = entry.find('atom:published', ns).text
                
                authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
                
                # Extract PDF link
                pdf_url = ""
                for link in entry.findall('atom:link', ns):
                    if link.attrib.get('title') == 'pdf' or 'pdf' in link.attrib.get('href', ''):
                        pdf_url = link.attrib.get('href')
                        break
                
                papers.append({
                    "title": title,
                    "authors": authors,
                    "summary": summary,
                    "published_at": published,
                    "pdf_url": pdf_url,
                    "source": "ArXiv Academic Database"
                })
                
            logger.info(f"Successfully retrieved {len(papers)} papers from ArXiv.")
        except Exception as e:
            logger.error(f"Failed to fetch papers from ArXiv: {e}")
            
        return papers

# Singleton
academic_research_agent = AcademicResearchAgent()
