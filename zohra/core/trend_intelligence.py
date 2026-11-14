"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — TREND INTELLIGENCE AGENT                     ║
║         Algorithm Audits & Viral Hashtag Extraction                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import List

logger = logging.getLogger("zohra.social.trend")

class TrendIntelligence:
    """
    Scans social media platforms and platform algorithms to identify
    trending hashtags and viral topics.
    """
    def get_trending_hashtags(self, topic: str) -> List[str]:
        logger.info(f"🔥 Scanning trends for topic: '{topic}'")
        
        t = topic.lower()
        if "gold" in t or "xau" in t:
            return ["goldtrading", "xauusd", "scalping", "forextrading", "algotrading"]
        elif "smc" in t or "liquidity" in t:
            return ["smartmoneyconcepts", "orderblocks", "liquiditypools", "innercircletrader"]
        elif "ai" in t or "python" in t:
            return ["ai", "pythoncoding", "machinelearning", "softwaredevelopment"]
            
        return ["trading", "investing", "finance", "wealth"]

# Singleton
trend_intelligence = TrendIntelligence()
