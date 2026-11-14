"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — KNOWLEDGE GRAPH ENGINE                     ║
║         Relational Concept Mapping & Semantic Linkage                ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
from typing import Dict, List, Any
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.research.graph")

class KnowledgeGraphEngine:
    """
    Builds and maintains the Zohra Knowledge Graph, connecting concepts
    (e.g., SMC, Wyckoff, Inflation) to form an ever-expanding web of knowledge.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def add_node(self, node_id: str, name: str, category: str, description: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO knowledge_nodes (id, name, category, description)
                    VALUES (?, ?, ?, ?)
                """, (node_id, name, category, description))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add node: {e}")
            return False

    def add_edge(self, source: str, target: str, relationship: str) -> bool:
        try:
            # Verify nodes exist first to maintain integrity
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM knowledge_nodes WHERE id = ?", (source,))
                if not cursor.fetchone():
                    # Create placeholder node
                    self.add_node(source, source.replace('_', ' ').capitalize(), "General", "Automated concept placeholder.")
                
                cursor.execute("SELECT 1 FROM knowledge_nodes WHERE id = ?", (target,))
                if not cursor.fetchone():
                    # Create placeholder node
                    self.add_node(target, target.replace('_', ' ').capitalize(), "General", "Automated concept placeholder.")
                
                cursor.execute("""
                    INSERT OR REPLACE INTO knowledge_edges (source, target, relationship)
                    VALUES (?, ?, ?)
                """, (source, target, relationship))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add edge: {e}")
            return False

    def get_graph(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns all nodes and edges in a format suitable for D3.js or SVG rendering."""
        nodes = []
        edges = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Fetch nodes
                cursor.execute("SELECT * FROM knowledge_nodes")
                nodes = [dict(row) for row in cursor.fetchall()]
                
                # Fetch edges
                cursor.execute("SELECT * FROM knowledge_edges")
                edges = [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to fetch knowledge graph: {e}")
            
        return {
            "nodes": nodes,
            "edges": edges
        }

# Singleton
knowledge_graph_engine = KnowledgeGraphEngine()
