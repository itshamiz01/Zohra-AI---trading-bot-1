"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — INTERNET RESEARCH AGENT                      ║
║            Public Wikipedia API & Web Search Crawler                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import urllib.request
import json
from typing import List, Dict, Any

logger = logging.getLogger("zohra.research.internet")

class InternetResearchAgent:
    """
    Queries public information sources (Wikipedia, DuckDuckGo) to research
    general topics, concepts, and macroeconomic history.
    """
    def search_web(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        results = []
        try:
            # Clean and format query for Wikipedia API
            formatted_query = urllib.parse.quote(query)
            url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={formatted_query}&utf8=&format=json"
            
            logger.info(f"Querying Wikipedia: {url}")
            
            # Perform HTTP request
            import ssl
            context = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers={'User-Agent': 'ZohraOS-Research-Agent/1.0'})
            with urllib.request.urlopen(req, context=context, timeout=8) as response:
                json_data = json.loads(response.read().decode('utf-8'))
                
            search_results = json_data.get("query", {}).get("search", [])
            for item in search_results[:limit]:
                title = item.get("title")
                snippet = item.get("snippet", "").replace('<span class="searchmatch">', '').replace('</span>', '')
                page_id = item.get("pageid")
                
                results.append({
                    "title": title,
                    "summary": snippet,
                    "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}",
                    "source": "Wikipedia Database",
                    "page_id": page_id
                })
                
            logger.info(f"Successfully retrieved {len(results)} search results from Wikipedia.")
        except Exception as e:
            logger.error(f"Failed to fetch data from Wikipedia: {e}")
            
        # Fallback to local mock knowledge base if search fails or is empty
        if not results:
            results = self._get_fallback_results(query)
            
        return results

    def _get_fallback_results(self, query: str) -> List[Dict[str, Any]]:
        """Provides local definitions for common trading terms when offline."""
        q = query.lower()
        if "smc" in q or "smart money" in q:
            return [{
                "title": "Smart Money Concepts (SMC)",
                "summary": "A trading methodology focusing on tracking institutional order flow, identifying liquidity sweeps, order blocks, and market structure shifts (BOS/CHoCH).",
                "url": "https://zohra.internal/wiki/SMC",
                "source": "Zohra Local Knowledge Base"
            }]
        elif "inflation" in q or "cpi" in q:
            return [{
                "title": "Inflation & Consumer Price Index",
                "summary": "Inflation measures the rate of increase in prices. Central banks adjust interest rates to control inflation, directly impacting currency valuations.",
                "url": "https://zohra.internal/wiki/Inflation",
                "source": "Zohra Local Knowledge Base"
            }]
        return [{
            "title": f"Research on: {query}",
            "summary": f"No active internet connection. Initialized offline research query for '{query}'.",
            "url": "https://zohra.internal/wiki/Offline",
            "source": "Zohra Local Knowledge Base"
        }]

# Singleton
internet_research_agent = InternetResearchAgent()
