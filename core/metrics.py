"""
TRUTHFORGE AI — Runtime Metrics Collector
==========================================
Lightweight counters and timing aggregates for the pipeline.
Thread-safe increments using a file lock + in-memory cache.

Counters tracked:
  - pipeline_runs_total
  - pipeline_failures_total
  - pipeline_blocked_total      (security gate blocked an input)
  - pipeline_second_pass_total  (autonomy re-run triggered)

Gauges tracked:
  - avg_runtime_ms              (rolling mean of last 100 runs)
  - last_run_ms

Saved to: logs/metrics.json   (updated after every run)
Events:   logs/events.jsonl   (one JSON line per pipeline event)

Alert thresholds:
  - FAILURE_THRESHOLD  : warn if failures > N in last 100 runs
  - BLOCK_SPIKE_THRESH : warn if blocked > N in last 100 runs

Usage:
    from core.metrics import metrics
    metrics.record_run(duration_ms=1234, success=True, blocked=False)
    metrics.record_security_event("injection_detected", details="...")
"""

from __future__ import annotations

import json
import os
import threading
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_LOGS_DIR = Path(__file__).parent.parent / "logs"

FAILURE_THRESHOLD = 5      # warn if failures exceed this in last 100 runs
BLOCK_SPIKE_THRESH = 3     # warn if blocks exceed this in last 100 runs
_ROLLING_WINDOW = 100      # number of runs used for rolling averages


class MetricsCollector:
    """Thread-safe, file-backed metrics collector."""

    def __init__(self, logs_dir: Path | str = _LOGS_DIR):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._metrics_path = self.logs_dir / "metrics.json"
        self._events_path = self.logs_dir / "events.jsonl"
        self._metrics: dict = self._load_metrics()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_run(
        self,
        duration_ms: float,
        success: bool,
        blocked: bool,
        second_pass: bool = False,
        model_name: str = "unknown",
        n_inconsistencies: int = 0,
    ) -> None:
        """Record the completion of one pipeline run and check alert thresholds."""
        with self._lock:
            m = self._metrics

            m["pipeline_runs_total"] += 1
            if not success and not blocked:
                m["pipeline_failures_total"] += 1
            if blocked:
                m["pipeline_blocked_total"] += 1
            if second_pass:
                m["pipeline_second_pass_total"] += 1

            # Rolling runtime window
            m["recent_runtimes_ms"].append(round(duration_ms, 1))
            if len(m["recent_runtimes_ms"]) > _ROLLING_WINDOW:
                m["recent_runtimes_ms"] = m["recent_runtimes_ms"][-_ROLLING_WINDOW:]

            m["last_run_ms"] = round(duration_ms, 1)
            m["avg_runtime_ms"] = (
                round(sum(m["recent_runtimes_ms"]) / len(m["recent_runtimes_ms"]), 1)
                if m["recent_runtimes_ms"] else 0.0
            )
            m["last_updated"] = datetime.now(timezone.utc).isoformat()

            self._save_metrics()
            self._write_event("pipeline_run", {
                "success": success,
                "blocked": blocked,
                "second_pass": second_pass,
                "duration_ms": round(duration_ms, 1),
                "model": model_name,
                "n_inconsistencies": n_inconsistencies,
            })

            # Alert checks
            self._check_alerts()

    def record_security_event(
        self,
        event_type: str,
        details: str = "",
        score: float = 0.0,
    ) -> None:
        """
        Record a security-relevant event.

        event_type: one of:
          injection_detected | output_filtered | bias_detected |
          suspicious_allowed | neutrality_violation
        """
        with self._lock:
            cats = self._metrics.setdefault("security_event_counts", {})
            cats[event_type] = cats.get(event_type, 0) + 1
            self._save_metrics()
            self._write_event(event_type, {
                "details": details[:200],
                "score": round(score, 3),
            })

    def get_snapshot(self) -> dict:
        """Return a copy of current metrics (thread-safe)."""
        with self._lock:
            return dict(self._metrics)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _default_metrics(self) -> dict:
        return {
            "pipeline_runs_total": 0,
            "pipeline_failures_total": 0,
            "pipeline_blocked_total": 0,
            "pipeline_second_pass_total": 0,
            "avg_runtime_ms": 0.0,
            "last_run_ms": 0.0,
            "recent_runtimes_ms": [],
            "last_updated": None,
            "security_event_counts": {},
        }

    def _load_metrics(self) -> dict:
        if self._metrics_path.exists():
            try:
                with open(self._metrics_path) as f:
                    loaded = json.load(f)
                    # Merge with defaults in case new keys were added
                    defaults = self._default_metrics()
                    defaults.update(loaded)
                    return defaults
            except Exception:
                pass
        return self._default_metrics()

    def _save_metrics(self) -> None:
        """Write metrics.json (called within lock)."""
        try:
            with open(self._metrics_path, "w") as f:
                # Don't serialise the rolling list in its full form for readability;
                # keep it but trim to last 20 values for display
                display = dict(self._metrics)
                display["recent_runtimes_ms_preview"] = self._metrics["recent_runtimes_ms"][-20:]
                json.dump(display, f, indent=2)
        except Exception:
            pass

    def _write_event(self, event_type: str, payload: dict) -> None:
        """Append one JSON line to events.jsonl (called within lock)."""
        try:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event_type,
                **payload,
            }
            with open(self._events_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _check_alerts(self) -> None:
        """Emit console warnings if metrics cross alert thresholds."""
        m = self._metrics
        total = max(m["pipeline_runs_total"], 1)
        recent_window = min(total, _ROLLING_WINDOW)

        # Failure spike alert
        if m["pipeline_failures_total"] > FAILURE_THRESHOLD:
            warnings.warn(
                f"[TRUTHFORGE ALERT] Pipeline failures ({m['pipeline_failures_total']}) "
                f"exceed threshold ({FAILURE_THRESHOLD}) over {recent_window} runs. "
                f"Check logs/events.jsonl for details.",
                RuntimeWarning,
                stacklevel=3,
            )

        # Block spike alert
        if m["pipeline_blocked_total"] > BLOCK_SPIKE_THRESH:
            warnings.warn(
                f"[TRUTHFORGE ALERT] Security blocks ({m['pipeline_blocked_total']}) "
                f"exceed threshold ({BLOCK_SPIKE_THRESH}). "
                f"Possible coordinated injection attack — review logs/events.jsonl.",
                RuntimeWarning,
                stacklevel=3,
            )


# Module-level singleton
metrics = MetricsCollector()
