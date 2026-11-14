"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — RESEARCH MEMORY STORE                      ║
║         Hybrid SQLite & Pure-Python Vector Similarity DB             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import sqlite3
import logging
import math
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.research.memory")

class ResearchMemory:
    """
    Manages the persistent storage of research projects, sources, citations,
    and a lightweight vector embedding collection for semantic search.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes all SQLite tables required for the Research Division."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. Research Projects
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS research_projects (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        created_at TEXT
                    )
                """)
                
                # 2. Research Sources (Webpages, PDFs, YouTube videos, Books)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS research_sources (
                        id TEXT PRIMARY KEY,
                        project_id TEXT,
                        source_type TEXT, -- 'WEBSITE', 'PDF', 'YOUTUBE', 'BOOK', 'NEWS'
                        title TEXT,
                        author TEXT,
                        url TEXT,
                        raw_content TEXT,
                        created_at TEXT,
                        FOREIGN KEY(project_id) REFERENCES research_projects(id)
                    )
                """)
                
                # 3. Citation Records
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS research_citations (
                        id TEXT PRIMARY KEY,
                        source_id TEXT,
                        title TEXT,
                        author TEXT,
                        url TEXT,
                        confidence_rating REAL,
                        created_at TEXT,
                        FOREIGN KEY(source_id) REFERENCES research_sources(id)
                    )
                """)
                
                # 4. Knowledge Graph Nodes
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_nodes (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT,
                        description TEXT
                    )
                """)
                
                # 5. Knowledge Graph Edges
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_edges (
                        source TEXT,
                        target TEXT,
                        relationship TEXT,
                        PRIMARY KEY (source, target, relationship),
                        FOREIGN KEY(source) REFERENCES knowledge_nodes(id),
                        FOREIGN KEY(target) REFERENCES knowledge_nodes(id)
                    )
                """)

                # 6. Vector Embeddings (for semantic search chunk storage)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vector_chunks (
                        id TEXT PRIMARY KEY,
                        source_id TEXT,
                        text_content TEXT,
                        embedding_json TEXT, -- JSON array of floats
                        FOREIGN KEY(source_id) REFERENCES research_sources(id)
                    )
                """)
                
                conn.commit()
            logger.info("Research Memory database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Research Memory database: {e}")

    # ─── RELATIONAL OPERATIONS ──────────────────────────────────────────
    
    def create_project(self, project_id: str, name: str, description: str = "") -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO research_projects (id, name, description, created_at)
                    VALUES (?, ?, ?, ?)
                """, (project_id, name, description, datetime.utcnow().isoformat()))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            return False

    def add_source(self, source_id: str, project_id: str, source_type: str, 
                   title: str, author: str, url: str, content: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO research_sources (id, project_id, source_type, title, author, url, raw_content, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (source_id, project_id, source_type, title, author, url, content, datetime.utcnow().isoformat()))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add source: {e}")
            return False

    def add_citation(self, citation_id: str, source_id: str, title: str, author: str, url: str, confidence: float) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO research_citations (id, source_id, title, author, url, confidence_rating, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (citation_id, source_id, title, author, url, confidence, datetime.utcnow().isoformat()))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add citation: {e}")
            return False

    # ─── LIGHTWEIGHT VECTOR OPERATIONS ──────────────────────────────────
    
    def add_vector_chunk(self, chunk_id: str, source_id: str, text: str, embedding: List[float]) -> bool:
        try:
            embedding_json = json.dumps(embedding)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO vector_chunks (id, source_id, text_content, embedding_json)
                    VALUES (?, ?, ?, ?)
                """, (chunk_id, source_id, text, embedding_json))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add vector chunk: {e}")
            return False

    def semantic_search(self, query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Performs cosine similarity search over all stored vector chunks in pure Python."""
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM vector_chunks")
                rows = cursor.fetchall()
                
                for row in rows:
                    chunk_id = row["id"]
                    source_id = row["source_id"]
                    text = row["text_content"]
                    emb = json.loads(row["embedding_json"])
                    
                    similarity = self._cosine_similarity(query_embedding, emb)
                    results.append({
                        "chunk_id": chunk_id,
                        "source_id": source_id,
                        "text": text,
                        "similarity": similarity
                    })
            
            # Sort by similarity descending
            results.sort(key=lambda x: x["similarity"], reverse=True)
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            
        return results[:limit]

    def generate_simple_embedding(self, text: str) -> List[float]:
        """
        Generates a deterministic pseudo-embedding vector using character-level n-grams.
        Ensures semantic similarity can be run offline without API keys.
        """
        vector_size = 128
        vector = [0.0] * vector_size
        
        # Simple hashing vectorizer
        text_clean = text.lower()
        for i in range(len(text_clean) - 2):
            trigram = text_clean[i:i+3]
            h = hash(trigram) % vector_size
            vector[h] += 1.0
            
        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
            
        return vector

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        if len(vec_a) != len(vec_b) or not vec_a:
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot_product / (norm_a * norm_b)

# Singleton
research_memory = ResearchMemory()
