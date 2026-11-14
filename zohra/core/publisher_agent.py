"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — PUBLISHER OUTREACH AGENT                     ║
║         Submission Pipelines, Query Letters, & Pitch Packages        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, List, Any
from zohra.core.business_memory import business_memory

logger = logging.getLogger("zohra.business.publisher")

class PublisherAgent:
    """
    Manages book publishing pipelines, submission logs, and drafts cover
    and query letters for outreach campaigns.
    """
    def generate_query_letter(self, book_title: str, genre: str, hook: str) -> Dict[str, str]:
        logger.info(f"📚 Generating query letter for book: '{book_title}'...")
        
        letter = (
            "Dear [Agent/Editor Name],\n\n"
            f"I am writing to pitch my completed {genre} novel, **{book_title}**.\n\n"
            f"{hook}\n\n"
            "The manuscript is fully polished, and I have attached the synopsis and first three chapters as requested. "
            "Thank you for your time and consideration.\n\n"
            "Sincerely,\n"
            "[Your Name]"
        )
        
        return {
            "title": book_title,
            "genre": genre,
            "query_letter": letter
        }

    def get_submissions(self) -> List[Dict[str, Any]]:
        """Returns all publisher contacts from the CRM."""
        contacts = business_memory.get_contacts()
        return [c for c in contacts if c.get("role") == "Senior Editor" or c.get("organization") == "Apex Publishing"]

# Singleton
publisher_agent = PublisherAgent()
