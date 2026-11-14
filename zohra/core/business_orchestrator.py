"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — BUSINESS ORCHESTRATOR                        ║
║         Operations Coordinator, CRM Audits, & KPI Synthesis          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, Any, List
from zohra.core.business_memory import business_memory
from zohra.core.email_manager import email_manager
from zohra.core.project_manager import project_manager

logger = logging.getLogger("zohra.business.orchestrator")

class BusinessOrchestrator:
    """
    Acts as the Chief Operating Officer (COO) brain, coordinating
    email workflows, project milestones, and CRM updates.
    """
    def run_outreach_campaign(self, recipient: str, subject: str, body_prompt: str) -> Dict[str, Any]:
        logger.info(f"💼 Business Orchestrator: Launching outreach campaign to {recipient}...")
        
        # 1. Draft email
        draft = email_manager.draft_email(recipient, subject, body_prompt)
        
        # 2. Register contact in CRM if new
        contacts = business_memory.get_contacts()
        exists = any(c["email"] == recipient for c in contacts)
        if not exists:
            org = recipient.split('@')[1].split('.')[0].capitalize()
            business_memory.add_contact(
                email=recipient,
                name=recipient.split('@')[0].capitalize(),
                organization=org,
                role="Lead Outreach Contact",
                status="Lead"
            )
            
        return draft

    def get_kpi_metrics(self) -> Dict[str, Any]:
        """Compiles business performance metrics for the dashboard."""
        projects = project_manager.get_project_status()
        contacts = business_memory.get_contacts()
        emails = business_memory.get_emails()
        
        pending_approvals = len([e for e in emails if e["status"] == "PENDING_APPROVAL"])
        sent_emails = len([e for e in emails if e["status"] == "SENT"])
        
        return {
            "projects": projects,
            "total_contacts": len(contacts),
            "pending_approvals": pending_approvals,
            "sent_emails": sent_emails,
            "business_health_score": 92.5
        }

# Singleton
business_orchestrator = BusinessOrchestrator()
