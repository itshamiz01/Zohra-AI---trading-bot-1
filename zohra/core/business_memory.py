"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — BUSINESS MEMORY STORE                      ║
║         Persistent Contacts, Projects, & Communication Logs          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.business.memory")

class BusinessMemory:
    """
    Manages Zohra's persistent business data, including CRM contacts,
    meeting/interaction notes, SaaS/publishing projects, and email drafts.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes SQLite tables for CRM, projects, and email queue."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. CRM Contacts
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS business_contacts (
                        email TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        organization TEXT,
                        role TEXT,
                        status TEXT -- 'Lead', 'Active', 'Archived'
                    )
                """)
                
                # 2. Contact Interactions
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS business_interactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        contact_email TEXT,
                        interaction_type TEXT, -- 'EMAIL', 'MEETING', 'CALL'
                        notes TEXT,
                        created_at TEXT,
                        FOREIGN KEY(contact_email) REFERENCES business_contacts(email)
                    )
                """)
                
                # 3. Business Projects
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS business_projects (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status TEXT, -- 'PLANNING', 'ACTIVE', 'COMPLETED', 'ON_HOLD'
                        kpis_json TEXT -- JSON object of KPIs
                    )
                """)
                
                # 4. Outbound Email Drafts
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS business_emails (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        recipient TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        body TEXT NOT NULL,
                        status TEXT NOT NULL, -- 'DRAFT', 'PENDING_APPROVAL', 'SENT'
                        created_at TEXT
                    )
                """)
                
                # Insert default business projects if empty
                cursor.execute("SELECT COUNT(*) FROM business_projects")
                if cursor.fetchone()[0] == 0:
                    projects = [
                        ("zohra_os", "Zohra Operating System", "ACTIVE", json.dumps({"progress_pct": 85, "tasks_completed": 12, "total_tasks": 15})),
                        ("book_buddy", "Book Buddy SaaS", "PLANNING", json.dumps({"progress_pct": 20, "tasks_completed": 2, "total_tasks": 10})),
                        ("trading_bot", "Institutional Trading Bot", "ACTIVE", json.dumps({"progress_pct": 95, "tasks_completed": 19, "total_tasks": 20}))
                    ]
                    cursor.executemany("INSERT INTO business_projects (id, name, status, kpis_json) VALUES (?, ?, ?, ?)", projects)
                    
                # Insert default contacts if empty
                cursor.execute("SELECT COUNT(*) FROM business_contacts")
                if cursor.fetchone()[0] == 0:
                    contacts = [
                        ("publisher@example.com", "John Editor", "Apex Publishing", "Senior Editor", "Lead"),
                        ("investor@example.com", "Sarah Venture", "Capital Ventures", "Partner", "Active")
                    ]
                    cursor.executemany("INSERT INTO business_contacts (email, name, organization, role, status) VALUES (?, ?, ?, ?, ?)", contacts)

                conn.commit()
            logger.info("Business Memory database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Business Memory database: {e}")

    def add_contact(self, email: str, name: str, organization: str, role: str, status: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO business_contacts (email, name, organization, role, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (email, name, organization, role, status))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add contact: {e}")
            return False

    def add_interaction(self, contact_email: str, interaction_type: str, notes: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO business_interactions (contact_email, interaction_type, notes, created_at)
                    VALUES (?, ?, ?, ?)
                """, (contact_email, interaction_type, notes, datetime.utcnow().isoformat()))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add interaction: {e}")
            return False

    def add_project(self, project_id: str, name: str, status: str, kpis: Dict[str, Any]) -> bool:
        try:
            kpis_json = json.dumps(kpis)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO business_projects (id, name, status, kpis_json)
                    VALUES (?, ?, ?, ?)
                """, (project_id, name, status, kpis_json))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add project: {e}")
            return False

    def add_email_draft(self, recipient: str, subject: str, body: str, status: str = "PENDING_APPROVAL") -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO business_emails (recipient, subject, body, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (recipient, subject, body, status, datetime.utcnow().isoformat()))
                conn.commit()
                return cursor.lastrowid or 0
        except Exception as e:
            logger.error(f"Failed to add email draft: {e}")
            return 0

    def get_contacts(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM business_contacts")
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get contacts: {e}")
        return results

    def get_projects(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM business_projects")
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get projects: {e}")
        return results

    def get_emails(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM business_emails ORDER BY id DESC")
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get emails: {e}")
        return results

# Singleton
business_memory = BusinessMemory()
