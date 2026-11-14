"""
╔══════════════════════════════════════════════════════════════════════╗
║                     ZOHRA — EMAIL MANAGER                            ║
║         Outbound Drafting & User-Gated Sending Pipeline              ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, Any
from zohra.core.business_memory import business_memory

logger = logging.getLogger("zohra.business.email")

class EmailManager:
    """
    Drafts and queues professional emails, requiring explicit user approval
    before transmission.
    """
    def draft_email(self, recipient: str, subject: str, body_prompt: str) -> Dict[str, Any]:
        logger.info(f"📧 Drafting email to {recipient} on topic: '{body_prompt}'")
        
        # Formulate a professional business email template
        salutation = f"Dear {recipient.split('@')[0].capitalize()}," if "@" in recipient else "Dear Sir/Madam,"
        
        body = (
            f"{salutation}\n\n"
            f"I am writing to follow up regarding our recent discussions. {body_prompt}\n\n"
            "Please let me know if you have any questions or if we can hop on a quick call to discuss this further.\n\n"
            "Best regards,\n"
            "Zohra OS Business Desk"
        )
        
        # Save as draft in database (Pending Approval)
        draft_id = business_memory.add_email_draft(recipient, subject, body, "PENDING_APPROVAL")
        
        # Log to timeline
        try:
            from zohra.core.cognitive_memory import cognitive_memory
            cognitive_memory.add_timeline_event(
                event_type="EMAIL_DRAFTED",
                description=f"Drafted pitch email to {recipient} | Subject: {subject}.",
                reference_id=str(draft_id)
            )
        except Exception as e:
            logger.error(f"Failed to log email draft to timeline: {e}")
            
        return {
            "draft_id": draft_id,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "status": "PENDING_APPROVAL"
        }

    def approve_and_send(self, draft_id: int) -> bool:
        """Approves a pending draft and marks it as sent."""
        try:
            import sqlite3
            from zohra.config.settings import DB_PATH
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE business_emails 
                    SET status = 'SENT' 
                    WHERE id = ? AND status = 'PENDING_APPROVAL'
                """, (draft_id,))
                conn.commit()
                
            logger.info(f"📧 Email draft #{draft_id} approved and marked as SENT.")
            
            # Log to timeline
            from zohra.core.cognitive_memory import cognitive_memory
            cognitive_memory.add_timeline_event(
                event_type="EMAIL_SENT",
                description=f"Sent approved email draft #{draft_id} to recipient.",
                reference_id=str(draft_id)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to approve email: {e}")
            return False

# Singleton
email_manager = EmailManager()
