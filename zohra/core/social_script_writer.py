"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — SOCIAL SCRIPT WRITER                         ║
║         Platform-Tailored Social Copywriting & Hook Generator       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, List, Any
from zohra.core.social_memory import social_memory

logger = logging.getLogger("zohra.social.writer")

class SocialScriptWriter:
    """
    Drafts copy, captions, and script outlines optimized for specific
    social media channels (X, Instagram, YouTube, LinkedIn).
    """
    def generate_post(self, platform: str, topic: str) -> Dict[str, Any]:
        logger.info(f"✍️ Drafting social content for {platform} on topic: '{topic}'")
        
        plat = platform.upper()
        title = f"Insights on {topic}"
        
        # 1. Generate platform-specific templates
        if plat == "X":
            body = (
                f"1/ Thread: Let's break down {topic}. Here is what you need to know to stay ahead.\n\n"
                f"2/ When analyzing {topic}, the key is looking at institutional footprints and volume sweeps.\n\n"
                f"3/ In conclusion, manage your risk and wait for confirmation. What are your thoughts on this? 👇"
            )
            tags = ["trading", "finance", "algotrading"]
        elif plat == "INSTAGRAM":
            body = (
                f"🔥 Deep Dive: {topic} 🔥\n\n"
                f"Swipe left to check out the core mechanics of {topic}. Understanding these levels "
                "separates retail traders from institutional players.\n\n"
                "Save this post for your next session! 💾"
            )
            tags = ["smc", "orderblocks", "forex"]
        elif plat == "LINKEDIN":
            body = (
                f"🎯 Microstructure Analysis: {topic}\n\n"
                f"In institutional finance, {topic} represents a crucial inflection point. "
                "By analyzing liquidity pools and order matching algorithms, we can build high-expectancy "
                "trading frameworks.\n\n"
                "Read our latest research report inside Zohra OS. What is your take on this?"
            )
            tags = ["quant", "finance", "algorithmictrading"]
        else: # YOUTUBE
            body = (
                f"[HOOK]\nStop trading {topic} until you watch this video. Here is why.\n\n"
                f"[BODY]\nHey everyone. Today we are diving deep into the mechanics of {topic}. "
                "We will show you exactly how Zohra OS indexes these zones and how you can capitalize on them.\n\n"
                f"[CTA]\nMake sure to like, subscribe, and leave a comment below with your questions!"
            )
            tags = ["gold", "trading", "algotrading"]
            
        # Save to queue as PENDING_APPROVAL
        content_id = social_memory.add_content(plat, title, body, tags, "PENDING_APPROVAL")
        
        return {
            "content_id": content_id,
            "platform": plat,
            "title": title,
            "body": body,
            "tags": tags,
            "status": "PENDING_APPROVAL"
        }

# Singleton
social_script_writer = SocialScriptWriter()
