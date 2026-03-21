"""
TRUTHFORGE AI — Run Metadata Tracker
======================================
Records a structured artifact for every pipeline run so results are
fully reproducible and traceable.

Each run artifact captures:
  - run_id          : unique UUID
  - model_name      : e.g. "claude-sonnet-4-6"
  - model_provider  : e.g. "anthropic"
  - prompt_versions : dict of agent → PROMPT_VERSION constant
  - timestamp       : ISO-8601 UTC
  - transcript_hash : SHA-256 of the raw transcript text
  - transcript_chars: character count
  - thread_id       : LangGraph session thread ID
  - result_summary  : {status, n_inconsistencies, n_entities, blocked}
  - duration_ms     : wall-clock time for the full pipeline run

Artifacts saved to: artifacts/runs/<run_id>.json

Usage:
    from core.run_metadata import RunMetadataTracker
    tracker = RunMetadataTracker()
    run_id = tracker.open_run(transcript, llm_config, thread_id)
    # ... pipeline executes ...
    tracker.close_run(run_id, final_state, duration_ms)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Prompt version constants — bump these when prompt text changes
# ---------------------------------------------------------------------------
PROMPT_VERSIONS: dict[str, str] = {
    "transcript_processing":    "v1.0",
    "timeline_reconstruction":  "v1.0",
    "consistency_analysis":     "v1.0",
    "explainability":           "v1.1",   # v1.1: fairness/bias improvements
    "security_input":           "v1.0",
    "security_output":          "v1.1",   # v1.1: bias pattern additions
}

_ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "runs"


class RunMetadataTracker:
    """Lightweight tracker — open a run before the pipeline, close it after."""

    def __init__(self, artifacts_dir: Path | str = _ARTIFACTS_DIR):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._open_runs: dict[str, dict] = {}

    def open_run(
        self,
        transcript: str,
        llm_config: dict | None,
        thread_id: str,
    ) -> str:
        """
        Start tracking a new run. Returns the run_id.

        Args:
            transcript: raw transcript text
            llm_config: LangGraph config dict (or None for fallback mode)
            thread_id: unique session thread ID

        Returns:
            run_id string (UUID hex prefix)
        """
        run_id = uuid.uuid4().hex[:16]
        cfg = (llm_config or {}).get("configurable", {})

        record: dict = {
            "run_id": run_id,
            "thread_id": thread_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_name": cfg.get("model", "fallback"),
            "model_provider": cfg.get("model_provider", "none"),
            "prompt_versions": PROMPT_VERSIONS.copy(),
            "transcript_hash": hashlib.sha256(transcript.encode()).hexdigest(),
            "transcript_chars": len(transcript),
            "status": "running",
            "result_summary": None,
            "duration_ms": None,
        }
        self._open_runs[run_id] = record
        return run_id

    def close_run(
        self,
        run_id: str,
        final_state: dict,
        duration_ms: float,
    ) -> None:
        """
        Finalize the run record and save it to disk.

        Args:
            run_id: returned by open_run()
            final_state: TruthForgeState after pipeline completion
            duration_ms: wall-clock time in milliseconds
        """
        record = self._open_runs.pop(run_id, None)
        if record is None:
            return

        blocked = final_state.get("security_input_blocked", False)
        error = final_state.get("error_state")
        n_inc = len(final_state.get("inconsistencies", []))
        n_ent = len(final_state.get("entities", []))
        n_high = sum(
            1 for i in final_state.get("inconsistencies", [])
            if i.get("severity") == "HIGH"
        )

        record.update({
            "status": "blocked" if blocked else ("error" if error else "success"),
            "duration_ms": round(duration_ms, 1),
            "result_summary": {
                "n_inconsistencies": n_inc,
                "n_high_severity": n_high,
                "n_entities": n_ent,
                "blocked": blocked,
                "error": str(error) if error else None,
                "report_chars": len(final_state.get("final_report", "")),
            },
        })

        path = self.artifacts_dir / f"{run_id}.json"
        with open(path, "w") as f:
            json.dump(record, f, indent=2)

    def load_run(self, run_id: str) -> Optional[dict]:
        """Load a previously saved run record by run_id."""
        path = self.artifacts_dir / f"{run_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def list_runs(self, limit: int = 50) -> list[dict]:
        """Return the most recent `limit` run records, newest first."""
        paths = sorted(
            self.artifacts_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        records = []
        for p in paths[:limit]:
            try:
                with open(p) as f:
                    records.append(json.load(f))
            except Exception:
                pass
        return records


# Module-level singleton
_tracker = RunMetadataTracker()


def open_run(transcript: str, llm_config: dict | None, thread_id: str) -> str:
    """Module-level helper — open a new run."""
    return _tracker.open_run(transcript, llm_config, thread_id)


def close_run(run_id: str, final_state: dict, duration_ms: float) -> None:
    """Module-level helper — close and persist a run."""
    _tracker.close_run(run_id, final_state, duration_ms)


def list_runs(limit: int = 50) -> list[dict]:
    """Module-level helper — list recent runs."""
    return _tracker.list_runs(limit)
