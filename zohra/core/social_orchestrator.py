"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — SOCIAL MEDIA ORCHESTRATOR                    ║
║         Campaign Coordination, Trend Audits, & Copy Synthesis        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, Any, List
from zohra.core.social_memory import social_memory
from zohra.core.social_script_writer import social_script_writer
from zohra.core.trend_intelligence import trend_intelligence

logger = logging.getLogger("zohra.social.orchestrator")

class SocialOrchestrator:
    """
    Coordinates the Social Media Division, combining trend analysis
    and copywriting into unified creative campaigns.
    """
    def create_campaign(self, platform: str, topic: str) -> Dict[str, Any]:
        logger.info(f"📣 Social Orchestrator: Launching campaign on {platform} for '{topic}'...")
        
        # 1. Get trending hashtags
        trends = trend_intelligence.get_trending_hashtags(topic)
        
        # 2. Generate post copy
        post_data = social_script_writer.generate_post(platform, topic)
        
        # Append trending tags
        full_tags = list(set(post_data["tags"] + trends))
        
        # Update record in DB with merged tags
        try:
            import sqlite3
            from zohra.config.settings import DB_PATH
            import json
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE social_content_queue 
                    SET tags_json = ? 
                    WHERE id = ?
                """, (json.dumps(full_tags), post_data["content_id"]))
                conn.commit()
            post_data["tags"] = full_tags
        except Exception as e:
            logger.error(f"Failed to update merged tags: {e}")
            
        # Log to timeline
        try:
            from zohra.core.cognitive_memory import cognitive_memory
            cognitive_memory.add_timeline_event(
                event_type="SOCIAL_CAMPAIGN_CREATED",
                description=f"Created {platform} creative campaign on '{topic}' | Tags: {', '.join(full_tags)}.",
                reference_id=str(post_data["content_id"])
            )
        except Exception as e:
            logger.error(f"Failed to log campaign to timeline: {e}")

        return post_data

    def get_channel_metrics(self) -> Dict[str, Any]:
        """Compiles channel analytics for the dashboard."""
        analytics = social_memory.get_analytics()
        queue = social_memory.get_content_queue()
        
        pending_approvals = len([p for p in queue if p["status"] == "PENDING_APPROVAL"])
        scheduled_posts = len([p for p in queue if p["status"] == "SCHEDULED"])
        
        # Calculate total views
        total_views = sum(a["views"] for a in analytics)
        total_engagement = sum(a["engagement"] for a in analytics)
        
        return {
            "total_views": total_views,
            "total_engagement": total_engagement,
            "pending_approvals": pending_approvals,
            "scheduled_posts": scheduled_posts,
            "growth_rate_pct": 14.2
        }

# Singleton
social_orchestrator = SocialOrchestrator()
