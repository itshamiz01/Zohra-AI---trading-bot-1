import os
import tempfile
import unittest
from datetime import datetime, timedelta

from zohra.memory.lifecycle_memory import LifecycleMemoryStore


class TestVolume4Memory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "memory.db")
        self.store = LifecycleMemoryStore(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_write_path_creates_pending_sync_log(self):
        memory = self.store.write_episodic_memory(
            "User prefers one percent max risk on EURUSD.",
            source_turn_id="turn-1",
            metadata={"category": "preference"},
        )

        self.assertIsNotNone(self.store.get_episodic(memory.id))
        self.assertEqual(self.store.get_sync_backlog_count(), 1)

        self.store.mark_vector_synced(memory.id)
        self.assertEqual(self.store.get_sync_backlog_count(), 0)

    def test_user_forget_deletes_solely_derived_semantic_fact(self):
        source = self.store.write_episodic_memory("Remember Henderson risk limit is one percent.")
        semantic_id = self.store.upsert_semantic_memory(
            "Henderson risk limit is one percent.",
            derived_from=[source.id],
            confidence=0.8,
        )

        self.assertTrue(self.store.user_forget_memory(source.id))
        self.assertIsNone(self.store.get_episodic(source.id))

        with self.store._connect() as conn:
            row = conn.execute("SELECT id FROM semantic_memory WHERE id=?", (semantic_id,)).fetchone()
        self.assertIsNone(row)

    def test_user_forget_narrows_partially_derived_semantic_fact(self):
        first = self.store.write_episodic_memory("Henderson usually trades EURUSD during London.")
        second = self.store.write_episodic_memory("Henderson usually trades EURUSD during New York.")
        semantic_id = self.store.upsert_semantic_memory(
            "Henderson usually trades EURUSD.",
            derived_from=[first.id, second.id],
            confidence=0.9,
        )

        self.assertTrue(self.store.user_forget_memory(first.id))

        with self.store._connect() as conn:
            row = conn.execute("SELECT derived_from_json FROM semantic_memory WHERE id=?", (semantic_id,)).fetchone()
        self.assertIn(second.id, row["derived_from_json"])
        self.assertNotIn(first.id, row["derived_from_json"])

    def test_forgetting_policy_blocks_active_backlink_then_purges_after_removed(self):
        old = self.store.write_episodic_memory("Temporary memory about a stale setup.")
        old_created = (datetime.utcnow() - timedelta(days=365)).isoformat()
        old_below = (datetime.utcnow() - timedelta(days=100)).isoformat()
        with self.store._connect() as conn:
            conn.execute(
                """
                UPDATE episodic_memory
                SET created_at=?, access_count=0, below_threshold_since=?
                WHERE id=?
                """,
                (old_created, old_below, old.id),
            )
        semantic_id = self.store.upsert_semantic_memory(
            "A stale setup existed.",
            derived_from=[old.id],
            confidence=0.7,
        )

        stats = self.store.run_forgetting_policy_sweep(
            now=datetime.utcnow(),
            purge_threshold=10.0,
            grace_period=timedelta(days=90),
        )
        self.assertEqual(stats["blocked_by_backlink"], 1)
        self.assertIsNotNone(self.store.get_episodic(old.id))

        self.store.delete_semantic_memory(semantic_id)
        stats = self.store.run_forgetting_policy_sweep(
            now=datetime.utcnow(),
            purge_threshold=10.0,
            grace_period=timedelta(days=90),
        )
        self.assertEqual(stats["purged"], 1)
        self.assertIsNone(self.store.get_episodic(old.id))

    def test_consolidation_extracts_semantic_memory_and_graph(self):
        created = (datetime.utcnow() - timedelta(hours=13)).isoformat()
        ids = []
        for suffix in ("London", "New York", "Asia"):
            mem = self.store.write_episodic_memory(
                f"Henderson Corp prefers EURUSD risk review during {suffix} session."
            )
            ids.append(mem.id)
        with self.store._connect() as conn:
            conn.executemany(
                "UPDATE episodic_memory SET created_at=? WHERE id=?",
                [(created, memory_id) for memory_id in ids],
            )

        stats = self.store.run_nightly_consolidation(now=datetime.utcnow())
        self.assertEqual(stats["episodic_processed"], 3)
        self.assertGreaterEqual(stats["semantic_written"], 1)

        hits = self.store.retrieve("What do we know about Henderson Corp?", token_budget=200)
        self.assertTrue(any("Henderson" in hit["content"] for hit in hits))


if __name__ == "__main__":
    unittest.main()
