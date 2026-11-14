# zohra/memory/vector_store.py
import os
import json
import logging
import sqlite3
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger("zohra.memory")

# Fallbacks
CHROMA_AVAILABLE = False
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    pass

SKLEARN_AVAILABLE = False
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    pass

class AIMemory:
    """
    Long-term Memory Engine for Zohra Command Center.
    Vectorizes and indexes historical trade setups, winning/losing patterns, and market behavior.
    """
    # 5 Explicit Memory Categories (Phase 8)
    MEMORY_STRATEGY = "strategy_memory"      # What strategies exist and their rules
    MEMORY_MARKET = "market_memory"          # What happened in the market before
    MEMORY_TRADE = "trade_memory"            # All trades ever taken
    MEMORY_ERROR = "error_memory"            # All mistakes and rejections
    MEMORY_IMPROVEMENT = "improvement_memory" # What changes improved performance

    def add_strategy_memory(self, strategy_id: str, context_text: str, metadata: dict):
        self.add_trade_experience(strategy_id, context_text, self.MEMORY_STRATEGY, metadata)

    def add_error_memory(self, error_id: str, context_text: str, metadata: dict):
        self.add_trade_experience(error_id, context_text, self.MEMORY_ERROR, metadata)

    def add_improvement_memory(self, improvement_id: str, context_text: str, metadata: dict):
        self.add_trade_experience(improvement_id, context_text, self.MEMORY_IMPROVEMENT, metadata)

    def query_errors(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.query_experience(query_text, category=self.MEMORY_ERROR, limit=limit)

    def query_improvements(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.query_experience(query_text, category=self.MEMORY_IMPROVEMENT, limit=limit)

    def __init__(self, db_path: str = None, chroma_path: str = None):
        from zohra.config.settings import settings
        self.db_path = db_path or settings.DB_PATH
        self.chroma_path = chroma_path or getattr(settings, "CHROMA_PATH", "logs/chroma_db_a")
        self._init_sqlite_memory_table()
        
        if CHROMA_AVAILABLE:
            try:
                self.client = chromadb.PersistentClient(path=self.chroma_path)
                self.collection = self.client.get_or_create_collection(
                    name="zohra_trade_memory",
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info("🧠 Long-term memory initialized with ChromaDB.")
            except Exception as e:
                logger.warning(f"Failed to init ChromaDB: {e}. Falling back to SQLite memory.")
                self.collection = None
        else:
            logger.info("🧠 ChromaDB not installed. Using SQLite + TFIDF/Numpy semantic memory fallback.")
            self.collection = None

    def _init_sqlite_memory_table(self):
        """Ensure local SQLite fallback table exists for memory entries."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_memory_entries (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    context_text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error creating SQLite memory tables: {e}")

    def add_trade_experience(self, trade_id: str, context_text: str, category: str, metadata: dict):
        """
        Stores experience in ChromaDB (if active) and logs to SQLite audit ledger.
        """
        timestamp = datetime.utcnow().isoformat()
        metadata_str = json.dumps(metadata)
        
        # SQLite storage (audit ledger)
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO ai_memory_entries (id, timestamp, context_text, category, metadata_json)
                VALUES (?, ?, ?, ?, ?)
            """, (trade_id, timestamp, context_text, category, metadata_str))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log experience to SQLite: {e}")

        # ChromaDB vector store storage
        if self.collection is not None:
            try:
                # Convert metadata keys to basic types (str, int, float, bool)
                flat_meta = {}
                for k, v in metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        flat_meta[k] = v
                    else:
                        flat_meta[k] = str(v)
                flat_meta["category"] = category
                flat_meta["timestamp"] = timestamp

                self.collection.add(
                    documents=[context_text],
                    metadatas=[flat_meta],
                    ids=[trade_id]
                )
                logger.info(f"Added trade experience to vector database: {trade_id}")
            except Exception as e:
                logger.error(f"ChromaDB addition error: {e}")

    def query_experience(self, query_text: str, category: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic query of experiences. Uses ChromaDB, or falls back to TFIDF + cosine similarity over SQLite logs.
        """
        # 1. Try ChromaDB
        if self.collection is not None:
            try:
                where_clause = {}
                if category:
                    where_clause = {"category": category}
                
                results = self.collection.query(
                    query_texts=[query_text],
                    n_results=limit,
                    where=where_clause if where_clause else None
                )
                
                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                ids = results.get("ids", [[]])[0]
                distances = results.get("distances", [[]])[0]
                
                memories = []
                for i in range(len(ids)):
                    memories.append({
                        "id": ids[i],
                        "text": documents[i],
                        "metadata": metadatas[i],
                        "distance": distances[i] if i < len(distances) else 0.0,
                        "score": round(1.0 - (distances[i] if i < len(distances) else 0.0), 3)
                    })
                return memories
            except Exception as e:
                logger.error(f"ChromaDB query failed: {e}. Falling back to SQLite search.")

        # 2. Fallback to SQL + TFIDF
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT id, context_text, category, metadata_json, timestamp FROM ai_memory_entries WHERE category = ?", (category,))
            else:
                cursor.execute("SELECT id, context_text, category, metadata_json, timestamp FROM ai_memory_entries")
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return []

            documents = [r["context_text"] for r in rows]
            
            if SKLEARN_AVAILABLE and len(documents) > 0:
                vectorizer = TfidfVectorizer()
                tfidf = vectorizer.fit_transform(documents)
                query_vec = vectorizer.transform([query_text])
                similarities = cosine_similarity(query_vec, tfidf).flatten()
                
                top_indices = np.argsort(similarities)[::-1][:limit]
                memories = []
                for idx in top_indices:
                    sim = float(similarities[idx])
                    if sim > 0.05:  # Relevance threshold
                        row = rows[idx]
                        memories.append({
                            "id": row["id"],
                            "text": row["context_text"],
                            "metadata": json.loads(row["metadata_json"]),
                            "score": round(sim, 3)
                        })
                return memories
            else:
                # Basic substring matching fallback
                memories = []
                words = query_text.lower().split()
                for r in rows:
                    score = sum(1 for w in words if w in r["context_text"].lower())
                    if score > 0:
                        memories.append({
                            "id": r["id"],
                            "text": r["context_text"],
                            "metadata": json.loads(r["metadata_json"]),
                            "score": round(score / len(words), 3)
                        })
                memories = sorted(memories, key=lambda x: x["score"], reverse=True)[:limit]
                return memories
                
        except Exception as e:
            logger.error(f"SQLite semantic search failure: {e}")
            return []

# Singleton instance
ai_memory = AIMemory()
