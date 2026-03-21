"""
TRUTHFORGE AI — Checkpointing and Session Memory
=================================================
v1.0: Wraps LangGraph's InMemorySaver for in-process sessions.
v1.1: Adds a local file-based PersistentMemoryStore for cross-run
      storage of extracted facts, timeline snapshots, and run summaries.

Memory layout on disk:
    memory/
      {run_id}_facts.json        ← structured facts extracted from transcript
      {run_id}_timeline.json     ← reconstructed timeline snapshot
      {run_id}_summary.json      ← run-level summary (reusable across sessions)
      index.json                 ← lightweight index of all stored runs

PersistentMemoryStore API:
    store = PersistentMemoryStore()
    store.save_facts(run_id, structured_facts)
    store.save_timeline(run_id, timeline)
    store.save_summary(run_id, summary_dict)
    store.load_facts(run_id)         → dict | None
    store.load_timeline(run_id)      → list | None
    store.load_summary(run_id)       → dict | None
    store.list_runs(limit=20)        → list[dict]   (index entries)
    store.get_recent_summaries(n=5)  → list[dict]   (most recent summaries)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_MEMORY_DIR = Path(__file__).parent.parent / "memory"


def build_checkpointer():
    """Return a LangGraph InMemorySaver instance."""
    from langgraph.checkpoint.memory import InMemorySaver
    return InMemorySaver()


def new_thread_id() -> str:
    """Generate a unique thread ID for each user session."""
    return f"session-{uuid.uuid4().hex[:12]}"


class PersistentMemoryStore:
    """
    File-based memory store for cross-run persistence.
    Saves intermediate results so they can be reused in later sessions
    or referenced in reports.
    """

    def __init__(self, memory_dir: Path | str = _MEMORY_DIR):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.memory_dir / "index.json"

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def save_facts(self, run_id: str, structured_facts: dict) -> None:
        """Persist extracted structured facts for this run."""
        self._write(f"{run_id}_facts.json", structured_facts)
        self._update_index(run_id, "facts")

    def save_timeline(self, run_id: str, timeline: list) -> None:
        """Persist reconstructed timeline snapshot for this run."""
        self._write(f"{run_id}_timeline.json", {"timeline": timeline})
        self._update_index(run_id, "timeline")

    def save_summary(self, run_id: str, summary: dict) -> None:
        """
        Persist a run-level summary for future reference.
        summary should contain at minimum: n_inconsistencies, n_entities,
        transcript_chars, model_name, timestamp.
        """
        summary["run_id"] = run_id
        summary.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._write(f"{run_id}_summary.json", summary)
        self._update_index(run_id, "summary", meta=summary)

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def load_facts(self, run_id: str) -> Optional[dict]:
        return self._read(f"{run_id}_facts.json")

    def load_timeline(self, run_id: str) -> Optional[list]:
        data = self._read(f"{run_id}_timeline.json")
        return data.get("timeline") if data else None

    def load_summary(self, run_id: str) -> Optional[dict]:
        return self._read(f"{run_id}_summary.json")

    def list_runs(self, limit: int = 20) -> list[dict]:
        """Return index entries for the most recent runs (newest first)."""
        index = self._load_index()
        return index[-limit:][::-1]

    def get_recent_summaries(self, n: int = 5) -> list[dict]:
        """Return the n most recent run summaries (with full data)."""
        runs = self.list_runs(limit=n * 2)  # over-fetch to compensate for missing files
        summaries = []
        for entry in runs:
            run_id = entry.get("run_id")
            if run_id:
                s = self.load_summary(run_id)
                if s:
                    summaries.append(s)
                if len(summaries) >= n:
                    break
        return summaries

    # ------------------------------------------------------------------
    # Chunk-level storage for long transcripts
    # ------------------------------------------------------------------

    def save_chunk(self, run_id: str, chunk_idx: int, chunk_data: dict) -> None:
        """Save an intermediate result for a transcript chunk (long document support)."""
        self._write(f"{run_id}_chunk_{chunk_idx:03d}.json", chunk_data)

    def load_chunks(self, run_id: str) -> list[dict]:
        """Load all chunks for a run, sorted by chunk index."""
        chunks = []
        for path in sorted(self.memory_dir.glob(f"{run_id}_chunk_*.json")):
            data = self._read(path.name)
            if data:
                chunks.append(data)
        return chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write(self, filename: str, data) -> None:
        try:
            with open(self.memory_dir / filename, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception:
            pass

    def _read(self, filename: str) -> Optional[dict]:
        path = self.memory_dir / filename
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return None

    def _load_index(self) -> list[dict]:
        if not self._index_path.exists():
            return []
        try:
            with open(self._index_path) as f:
                return json.load(f)
        except Exception:
            return []

    def _update_index(self, run_id: str, data_type: str, meta: dict | None = None) -> None:
        """Add or update an index entry for run_id."""
        try:
            index = self._load_index()
            # Find existing entry or create new
            entry = next((e for e in index if e.get("run_id") == run_id), None)
            if entry is None:
                entry = {
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data_types": [],
                }
                index.append(entry)
            if data_type not in entry["data_types"]:
                entry["data_types"].append(data_type)
            if meta:
                entry.update({k: v for k, v in meta.items()
                               if k in ("n_inconsistencies", "n_entities",
                                        "model_name", "transcript_chars")})
            # Keep index to last 500 entries
            if len(index) > 500:
                index = index[-500:]
            with open(self._index_path, "w") as f:
                json.dump(index, f, indent=2)
        except Exception:
            pass


# Module-level singleton
memory_store = PersistentMemoryStore()
