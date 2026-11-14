from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from zohra.config import settings

logger = logging.getLogger("zohra.memory.lifecycle")


def utcnow() -> datetime:
    return datetime.utcnow()


def iso(dt: Optional[datetime] = None) -> str:
    return (dt or utcnow()).isoformat()


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def json_loads(value: Optional[str], fallback: Any):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", name.lower())).strip()


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    memory_type: str
    content: str
    source_turn_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0
    retain_score: float = 0.0
    pinned: bool = False
    consolidated_at: Optional[str] = None
    below_threshold_since: Optional[str] = None
    metadata: Dict[str, Any] = None


class LifecycleMemoryStore:
    """
    Volume 4 memory implementation for local-first lifecycle storage.

    SQLite is used as the durable source of truth in this repository. The
    qdrant_sync_log table mirrors the Postgres/Qdrant protocol from the spec
    so async vector sync and hard-delete verification remain observable.
    """

    DECAY_LAMBDA = 0.035
    PURGE_THRESHOLD = 0.08
    GRACE_PERIOD = timedelta(days=90)
    MIN_CLUSTER_SIZE_FOR_PATTERN = 3
    CLUSTER_SIMILARITY_THRESHOLD = 0.42
    DISTILL_CONFIDENCE_THRESHOLD = 0.55

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DB_PATH
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    source_turn_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    retain_score REAL NOT NULL DEFAULT 1.0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    consolidated_at TEXT,
                    below_threshold_since TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    derived_from_json TEXT NOT NULL DEFAULT '[]',
                    superseded_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS procedural_memory (
                    id TEXT PRIMARY KEY,
                    instruction TEXT NOT NULL,
                    reinforcement_count INTEGER NOT NULL DEFAULT 1,
                    derived_from_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS memory_qdrant_sync_log (
                    memory_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    postgres_state TEXT NOT NULL,
                    qdrant_state TEXT NOT NULL,
                    last_attempt_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(memory_id, memory_type)
                );

                CREATE TABLE IF NOT EXISTS memory_kg_entities (
                    id TEXT PRIMARY KEY,
                    normalized_name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(normalized_name, entity_type)
                );

                CREATE TABLE IF NOT EXISTS memory_kg_edges (
                    id TEXT PRIMARY KEY,
                    from_entity_id TEXT NOT NULL,
                    to_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    source_memory_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(from_entity_id) REFERENCES memory_kg_entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(to_entity_id) REFERENCES memory_kg_entities(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_episodic_consolidated ON episodic_memory(consolidated_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_episodic_retain ON episodic_memory(pinned, retain_score);
                CREATE INDEX IF NOT EXISTS idx_sync_state ON memory_qdrant_sync_log(qdrant_state);
                CREATE INDEX IF NOT EXISTS idx_edges_source_memory ON memory_kg_edges(source_memory_id);
                """
            )

    def write_episodic_memory(
        self,
        content: str,
        source_turn_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
    ) -> MemoryRecord:
        memory_id = memory_id or f"mem_{uuid.uuid4().hex}"
        now = iso()
        metadata = metadata or {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episodic_memory
                    (id, content, source_turn_id, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory_id, content, source_turn_id, now, now, json_dumps(metadata)),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_qdrant_sync_log
                    (memory_id, memory_type, postgres_state, qdrant_state, last_attempt_at, attempt_count)
                VALUES (?, 'episodic', 'written', 'pending', ?, 0)
                """,
                (memory_id, now),
            )
        return self.get_episodic(memory_id)

    def mark_vector_synced(self, memory_id: str, memory_type: str = "episodic") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_qdrant_sync_log
                SET qdrant_state='synced', last_attempt_at=?, attempt_count=attempt_count+1
                WHERE memory_id=? AND memory_type=?
                """,
                (iso(), memory_id, memory_type),
            )

    def mark_vector_sync_failed(self, memory_id: str, memory_type: str = "episodic") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_qdrant_sync_log
                SET last_attempt_at=?, attempt_count=attempt_count+1
                WHERE memory_id=? AND memory_type=?
                """,
                (iso(), memory_id, memory_type),
            )

    def get_sync_backlog_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM memory_qdrant_sync_log
                WHERE qdrant_state IN ('pending', 'delete_pending')
                """
            ).fetchone()
            return int(row["cnt"] if row else 0)

    def get_episodic(self, memory_id: str) -> Optional[MemoryRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM episodic_memory WHERE id=?", (memory_id,)).fetchone()
        return self._row_to_episodic(row) if row else None

    def _row_to_episodic(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            memory_type="episodic",
            content=row["content"],
            source_turn_id=row["source_turn_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            access_count=int(row["access_count"] or 0),
            retain_score=float(row["retain_score"] or 0.0),
            pinned=bool(row["pinned"]),
            consolidated_at=row["consolidated_at"],
            below_threshold_since=row["below_threshold_since"],
            metadata=json_loads(row["metadata_json"], {}),
        )

    def compute_retain_score(self, memory: MemoryRecord, now: Optional[datetime] = None) -> float:
        now = now or utcnow()
        created = parse_dt(memory.created_at) or now
        days_old = max(0, (now - created).days)
        recency = math.exp(-self.DECAY_LAMBDA * days_old)
        frequency = math.log1p(memory.access_count)
        pin = 100.0 if memory.pinned else 0.0
        return recency + frequency + pin

    def has_active_derivation_backlink(self, memory_id: str) -> bool:
        with self._connect() as conn:
            semantic_rows = conn.execute("SELECT derived_from_json FROM semantic_memory").fetchall()
            procedural_rows = conn.execute("SELECT derived_from_json FROM procedural_memory").fetchall()
        for row in list(semantic_rows) + list(procedural_rows):
            if memory_id in json_loads(row["derived_from_json"], []):
                return True
        return False

    def run_forgetting_policy_sweep(
        self,
        now: Optional[datetime] = None,
        purge_threshold: Optional[float] = None,
        grace_period: Optional[timedelta] = None,
    ) -> Dict[str, int]:
        now = now or utcnow()
        purge_threshold = self.PURGE_THRESHOLD if purge_threshold is None else purge_threshold
        grace_period = self.GRACE_PERIOD if grace_period is None else grace_period
        stats = {"scored": 0, "grace_started": 0, "rescued": 0, "purged": 0, "blocked_by_backlink": 0}

        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM episodic_memory WHERE pinned=0").fetchall()

        for row in rows:
            memory = self._row_to_episodic(row)
            score = self.compute_retain_score(memory, now)
            stats["scored"] += 1

            if score < purge_threshold:
                if self.has_active_derivation_backlink(memory.id):
                    self._update_retain_state(memory.id, score, memory.below_threshold_since)
                    stats["blocked_by_backlink"] += 1
                    continue
                if memory.below_threshold_since is None:
                    self._update_retain_state(memory.id, score, iso(now))
                    stats["grace_started"] += 1
                else:
                    threshold_started = parse_dt(memory.below_threshold_since) or now
                    if now - threshold_started > grace_period:
                        self.hard_delete_memory(memory.id)
                        stats["purged"] += 1
                    else:
                        self._update_retain_state(memory.id, score, memory.below_threshold_since)
            else:
                if memory.below_threshold_since is not None:
                    stats["rescued"] += 1
                self._update_retain_state(memory.id, score, None)
        return stats

    def _update_retain_state(self, memory_id: str, retain_score: float, below_threshold_since: Optional[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE episodic_memory
                SET retain_score=?, below_threshold_since=?, updated_at=?
                WHERE id=?
                """,
                (retain_score, below_threshold_since, iso(), memory_id),
            )

    def increment_access(self, memory_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE episodic_memory
                SET access_count=access_count+1, below_threshold_since=NULL, updated_at=?
                WHERE id=?
                """,
                (iso(), memory_id),
            )

    def hard_delete_memory(self, memory_id: str, memory_type: str = "episodic") -> bool:
        if memory_type != "episodic":
            raise ValueError("Only episodic hard-delete is implemented by Volume 4 user deletion.")
        if self.has_active_derivation_backlink(memory_id):
            raise ValueError(f"Cannot delete episodic memory {memory_id}: active derived_from backlink exists.")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_qdrant_sync_log
                    (memory_id, memory_type, postgres_state, qdrant_state, last_attempt_at, attempt_count)
                VALUES (?, 'episodic', 'deleted', 'delete_pending', ?, 0)
                """,
                (memory_id, iso()),
            )
            conn.execute("DELETE FROM memory_kg_edges WHERE source_memory_id=?", (memory_id,))
            conn.execute("DELETE FROM episodic_memory WHERE id=?", (memory_id,))
            conn.execute(
                """
                UPDATE memory_qdrant_sync_log
                SET qdrant_state='delete_confirmed', last_attempt_at=?, attempt_count=attempt_count+1
                WHERE memory_id=? AND memory_type='episodic'
                """,
                (iso(), memory_id),
            )
        return self.get_episodic(memory_id) is None

    def user_forget_memory(self, memory_id: str) -> bool:
        with self._connect() as conn:
            semantic_rows = conn.execute("SELECT id, derived_from_json FROM semantic_memory").fetchall()

        for row in semantic_rows:
            derived_from = json_loads(row["derived_from_json"], [])
            if memory_id not in derived_from:
                continue
            if len(derived_from) <= 1:
                self.delete_semantic_memory(row["id"])
            else:
                narrowed = [item for item in derived_from if item != memory_id]
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE semantic_memory SET derived_from_json=?, updated_at=? WHERE id=?",
                        (json_dumps(narrowed), iso(), row["id"]),
                    )

        return self.hard_delete_memory(memory_id)

    def delete_semantic_memory(self, semantic_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM semantic_memory WHERE id=?", (semantic_id,))
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_qdrant_sync_log
                    (memory_id, memory_type, postgres_state, qdrant_state, last_attempt_at, attempt_count)
                VALUES (?, 'semantic', 'deleted', 'delete_confirmed', ?, 1)
                """,
                (semantic_id, iso()),
            )

    def upsert_semantic_memory(
        self,
        statement: str,
        derived_from: Sequence[str],
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
    ) -> str:
        memory_id = memory_id or f"sem_{uuid.uuid4().hex}"
        now = iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory
                    (id, statement, confidence, derived_from_json, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM semantic_memory WHERE id=?), ?), ?, ?)
                """,
                (
                    memory_id,
                    statement,
                    confidence,
                    json_dumps(list(derived_from)),
                    memory_id,
                    now,
                    now,
                    json_dumps(metadata or {}),
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_qdrant_sync_log
                    (memory_id, memory_type, postgres_state, qdrant_state, last_attempt_at, attempt_count)
                VALUES (?, 'semantic', 'written', 'pending', ?, 0)
                """,
                (memory_id, now),
            )
        return memory_id

    def upsert_procedural_memory(
        self,
        instruction: str,
        derived_from: Sequence[str],
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
    ) -> str:
        now = iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, reinforcement_count FROM procedural_memory WHERE lower(instruction)=lower(?)",
                (instruction,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE procedural_memory
                    SET reinforcement_count=?, derived_from_json=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        int(existing["reinforcement_count"]) + 1,
                        json_dumps(sorted(set(derived_from))),
                        now,
                        existing["id"],
                    ),
                )
                return existing["id"]

            memory_id = memory_id or f"proc_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO procedural_memory
                    (id, instruction, reinforcement_count, derived_from_json, created_at, updated_at, metadata_json)
                VALUES (?, ?, 1, ?, ?, ?, ?)
                """,
                (memory_id, instruction, json_dumps(list(derived_from)), now, now, json_dumps(metadata or {})),
            )
        return memory_id

    def run_nightly_consolidation(
        self,
        now: Optional[datetime] = None,
        min_age: timedelta = timedelta(hours=12),
    ) -> Dict[str, int]:
        now = now or utcnow()
        cutoff = iso(now - min_age)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM episodic_memory
                WHERE consolidated_at IS NULL AND created_at <= ?
                ORDER BY created_at ASC
                """,
                (cutoff,),
            ).fetchall()
        memories = [self._row_to_episodic(row) for row in rows]
        clusters = self.cluster_by_similarity(memories)
        semantic_written = 0
        procedural_written = 0

        for cluster in clusters:
            if len(cluster) < self.MIN_CLUSTER_SIZE_FOR_PATTERN:
                continue
            statement, confidence = self.distill_pattern(cluster)
            if confidence < self.DISTILL_CONFIDENCE_THRESHOLD:
                continue
            if self._looks_procedural(statement):
                self.upsert_procedural_memory(statement, [m.id for m in cluster], {"source": "nightly_consolidation"})
                procedural_written += 1
            else:
                self.upsert_semantic_memory(statement, [m.id for m in cluster], confidence, {"source": "nightly_consolidation"})
                semantic_written += 1

        self.extract_entities_and_relations(memories)
        if memories:
            with self._connect() as conn:
                conn.executemany(
                    "UPDATE episodic_memory SET consolidated_at=?, updated_at=? WHERE id=?",
                    [(iso(now), iso(now), memory.id) for memory in memories],
                )

        return {
            "episodic_processed": len(memories),
            "clusters": len(clusters),
            "semantic_written": semantic_written,
            "procedural_written": procedural_written,
        }

    def cluster_by_similarity(self, memories: Sequence[MemoryRecord]) -> List[List[MemoryRecord]]:
        clusters: List[List[MemoryRecord]] = []
        for memory in memories:
            placed = False
            for cluster in clusters:
                best = max(self.text_similarity(memory.content, item.content) for item in cluster)
                if best >= self.CLUSTER_SIMILARITY_THRESHOLD:
                    cluster.append(memory)
                    placed = True
                    break
            if not placed:
                clusters.append([memory])
        return clusters

    def distill_pattern(self, cluster: Sequence[MemoryRecord]) -> Tuple[str, float]:
        words_by_memory = [set(self._tokenize(memory.content)) for memory in cluster]
        common_words = set.intersection(*words_by_memory) if words_by_memory else set()
        common_words = {word for word in common_words if len(word) > 3}
        confidence = min(0.95, 0.45 + 0.12 * len(cluster) + 0.03 * len(common_words))
        first = cluster[0].content.strip().split(".")[0][:180]
        if common_words:
            topic = ", ".join(sorted(list(common_words))[:5])
            return f"Repeated memory pattern around {topic}: {first}", confidence
        return f"Repeated memory pattern: {first}", confidence

    def extract_entities_and_relations(self, episodic_batch: Sequence[MemoryRecord]) -> Dict[str, int]:
        nodes = 0
        edges = 0
        for memory in episodic_batch:
            entities = self.ner_extract(memory.content)
            entity_ids = []
            for entity in entities:
                entity_id, created = self.kg_upsert_entity(entity["name"], entity["type"])
                entity_ids.append(entity_id)
                nodes += int(created)
            for left, right in self.infer_relations(entity_ids):
                self.kg_upsert_edge(left, right, "co_occurs_with", memory.id)
                edges += 1
        return {"nodes_created": nodes, "edges_created": edges}

    def ner_extract(self, content: str) -> List[Dict[str, str]]:
        candidates = re.findall(r"\b(?:[A-Z][a-zA-Z0-9&.-]+)(?:\s+[A-Z][a-zA-Z0-9&.-]+){0,3}\b", content)
        entities = []
        seen = set()
        for candidate in candidates:
            cleaned = candidate.strip()
            if len(cleaned) < 3:
                continue
            normalized = normalize_entity_name(cleaned)
            if normalized in seen:
                continue
            seen.add(normalized)
            entity_type = "symbol" if cleaned.upper() == cleaned and len(cleaned) <= 8 else "entity"
            entities.append({"name": cleaned, "type": entity_type})
        return entities[:12]

    def kg_upsert_entity(self, name: str, entity_type: str) -> Tuple[str, bool]:
        normalized = normalize_entity_name(name)
        now = iso()
        with self._connect() as conn:
            exact = conn.execute(
                "SELECT id FROM memory_kg_entities WHERE normalized_name=? AND entity_type=?",
                (normalized, entity_type),
            ).fetchone()
            if exact:
                conn.execute("UPDATE memory_kg_entities SET updated_at=? WHERE id=?", (now, exact["id"]))
                return exact["id"], False

            rows = conn.execute(
                "SELECT id, normalized_name FROM memory_kg_entities WHERE entity_type=?",
                (entity_type,),
            ).fetchall()
            for row in rows:
                ratio = SequenceMatcher(None, normalized, row["normalized_name"]).ratio()
                distance_like = 1.0 - ratio
                if ratio >= 0.86 or distance_like <= 0.18:
                    conn.execute("UPDATE memory_kg_entities SET updated_at=? WHERE id=?", (now, row["id"]))
                    return row["id"], False

            entity_id = f"ent_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO memory_kg_entities
                    (id, normalized_name, display_name, entity_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entity_id, normalized, name, entity_type, now, now),
            )
            return entity_id, True

    def infer_relations(self, entity_ids: Sequence[str]) -> List[Tuple[str, str]]:
        pairs = []
        for idx, left in enumerate(entity_ids):
            for right in entity_ids[idx + 1:]:
                if left != right:
                    pairs.append((left, right))
        return pairs[:20]

    def kg_upsert_edge(self, from_entity_id: str, to_entity_id: str, relation_type: str, source_memory: str) -> str:
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM memory_kg_edges
                WHERE from_entity_id=? AND to_entity_id=? AND relation_type=? AND source_memory_id=?
                """,
                (from_entity_id, to_entity_id, relation_type, source_memory),
            ).fetchone()
            if existing:
                return existing["id"]
            edge_id = f"edge_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO memory_kg_edges
                    (id, from_entity_id, to_entity_id, relation_type, source_memory_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (edge_id, from_entity_id, to_entity_id, relation_type, source_memory, iso()),
            )
            return edge_id

    def retrieve(self, query: str, scope: Optional[str] = None, token_budget: int = 1000, limit: int = 10) -> List[Dict[str, Any]]:
        query_tokens = set(self._tokenize(query))
        vector_hits = self._text_search(query, scope=scope, limit=50)
        graph_hits = self._graph_search(query)
        by_id: Dict[str, Dict[str, Any]] = {}
        for hit in vector_hits + graph_hits:
            current = by_id.get(hit["id"])
            if not current or hit["score"] > current["score"]:
                by_id[hit["id"]] = hit

        ranked = sorted(
            by_id.values(),
            key=lambda item: (
                item["score"],
                len(query_tokens.intersection(set(self._tokenize(item.get("content", ""))))),
            ),
            reverse=True,
        )
        fitted = self._fit_to_token_budget(ranked, token_budget)[:limit]
        for item in fitted:
            if item["type"] == "episodic":
                self.increment_access(item["id"])
        return fitted

    def _text_search(self, query: str, scope: Optional[str], limit: int) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        query_tokens = set(self._tokenize(query))
        with self._connect() as conn:
            episodic_rows = conn.execute("SELECT * FROM episodic_memory").fetchall() if scope in (None, "episodic", "all") else []
            semantic_rows = conn.execute("SELECT * FROM semantic_memory").fetchall() if scope in (None, "semantic", "all") else []
            procedural_rows = conn.execute("SELECT * FROM procedural_memory").fetchall() if scope in (None, "procedural", "all") else []

        for row in episodic_rows:
            score = self._lexical_score(query_tokens, row["content"])
            if score > 0:
                hits.append({"id": row["id"], "type": "episodic", "content": row["content"], "score": score})
        for row in semantic_rows:
            score = self._lexical_score(query_tokens, row["statement"])
            if score > 0:
                hits.append({"id": row["id"], "type": "semantic", "content": row["statement"], "score": score})
        for row in procedural_rows:
            score = self._lexical_score(query_tokens, row["instruction"])
            if score > 0:
                hits.append({"id": row["id"], "type": "procedural", "content": row["instruction"], "score": score})
        return sorted(hits, key=lambda item: item["score"], reverse=True)[:limit]

    def _graph_search(self, query: str) -> List[Dict[str, Any]]:
        entities = self.ner_extract(query)
        if not entities:
            return []
        memory_ids = set()
        with self._connect() as conn:
            for entity in entities:
                normalized = normalize_entity_name(entity["name"])
                node = conn.execute(
                    "SELECT id FROM memory_kg_entities WHERE normalized_name=?",
                    (normalized,),
                ).fetchone()
                if not node:
                    continue
                frontier = {node["id"]}
                visited = set()
                for _ in range(2):
                    next_frontier = set()
                    for entity_id in frontier:
                        if entity_id in visited:
                            continue
                        visited.add(entity_id)
                        rows = conn.execute(
                            """
                            SELECT from_entity_id, to_entity_id, source_memory_id
                            FROM memory_kg_edges
                            WHERE from_entity_id=? OR to_entity_id=?
                            """,
                            (entity_id, entity_id),
                        ).fetchall()
                        for row in rows:
                            memory_ids.add(row["source_memory_id"])
                            next_frontier.add(row["from_entity_id"])
                            next_frontier.add(row["to_entity_id"])
                    frontier = next_frontier - visited

            hits = []
            for memory_id in memory_ids:
                row = conn.execute("SELECT * FROM episodic_memory WHERE id=?", (memory_id,)).fetchone()
                if row:
                    hits.append({"id": row["id"], "type": "episodic", "content": row["content"], "score": 0.35})
        return hits

    def _fit_to_token_budget(self, hits: Sequence[Dict[str, Any]], token_budget: int) -> List[Dict[str, Any]]:
        fitted = []
        used = 0
        for hit in hits:
            estimate = max(1, len(hit.get("content", "").split()))
            if used + estimate > token_budget:
                break
            fitted.append(hit)
            used += estimate
        return fitted

    def _tokenize(self, text: str) -> List[str]:
        return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]

    def _lexical_score(self, query_tokens: set, text: str) -> float:
        if not query_tokens:
            return 0.0
        text_tokens = set(self._tokenize(text))
        if not text_tokens:
            return 0.0
        overlap = len(query_tokens.intersection(text_tokens))
        return overlap / max(1, len(query_tokens))

    def text_similarity(self, left: str, right: str) -> float:
        left_tokens = set(self._tokenize(left))
        right_tokens = set(self._tokenize(right))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens.intersection(right_tokens)) / len(left_tokens.union(right_tokens))

    def _looks_procedural(self, statement: str) -> bool:
        lowered = statement.lower()
        return any(marker in lowered for marker in ("always", "when ", "if ", "rule", "process", "procedure"))


lifecycle_memory = LifecycleMemoryStore()
