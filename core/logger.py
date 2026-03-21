"""
TRUTHFORGE AI — Structured Audit Logger
Uses structlog for JSON-formatted, correlation-id-tagged entries.
All agent nodes call audit() to append to the TruthForgeState audit_log.

Also writes JSON-line events to logs/events.jsonl for monitoring.
"""

from __future__ import annotations
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False

_LOGS_DIR = Path(__file__).parent.parent / "logs"
_EVENTS_FILE = _LOGS_DIR / "events.jsonl"


def _write_jsonl_event(agent: str, event: str, **kwargs) -> None:
    """Append a JSON-line entry to logs/events.jsonl (best-effort, never raises)."""
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "event": event,
            **{k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool, type(None)))},
        }
        with open(_EVENTS_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _configure_structlog() -> None:
    if not _HAS_STRUCTLOG:
        return
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


_configure_structlog()


def get_logger(name: str = "truthforge"):
    """Return a structlog logger (or stdlib fallback)."""
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    return logging.getLogger(name)


def audit(agent_name: str, event: str, **kwargs) -> str:
    """
    Produce a single audit log entry string suitable for appending to
    TruthForgeState.audit_log.  Also emits to stdout via structlog
    and writes to logs/events.jsonl for monitoring.
    """
    ts = datetime.now(timezone.utc).isoformat()
    entry_id = str(uuid.uuid4())[:8]
    details = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    line = f"[{ts}] [{entry_id}] [{agent_name}] {event}"
    if details:
        line += f" | {details}"
    logger = get_logger(agent_name)
    logger.info(event, agent=agent_name, entry_id=entry_id, **kwargs)
    # Persist to JSONL for monitoring/alerting
    _write_jsonl_event(agent_name, event, entry_id=entry_id, **kwargs)
    return line
