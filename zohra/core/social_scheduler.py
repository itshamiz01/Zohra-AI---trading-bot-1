"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — SOCIAL PUBLISHING SCHEDULER                  ║
║         Content Calendar Queue & Approval Gated Posting              ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from zohra.core.social_memory import social_memory

logger = logging.getLogger("zohra.social.scheduler")

class SocialScheduler:
    """
    Manages the publishing queue, letting the user transition drafts
    from PENDING_APPROVAL to SCHEDULED or PUBLISHED.
    """
    def approve_post(self, post_id: int) -> bool:
        try:
            success = social_memory.update_content_status(post_id, "SCHEDULED")
            if success:
                logger.info(f"📅 Social Post #{post_id} approved and marked as SCHEDULED.")
                
                # Log timeline event
                try:
                    from zohra.core.cognitive_memory import cognitive_memory
                    cognitive_memory.add_timeline_event(
                        event_type="SOCIAL_POST_APPROVED",
                        description=f"Approved and scheduled social media post #{post_id}.",
                        reference_id=str(post_id)
                    )
                except Exception as e:
                    logger.error(f"Failed to log post approval to timeline: {e}")
                return True
        except Exception as e:
            logger.error(f"Failed to approve social post: {e}")
        return False

# Singleton
social_scheduler = SocialScheduler()
