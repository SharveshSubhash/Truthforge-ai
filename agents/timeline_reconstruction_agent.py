"""
TRUTHFORGE AI — Timeline Reconstruction Agent
================================================================
Takes structured facts (events extracted by the Transcript Processing Agent)
and organises them into a coherent, normalised chronological timeline.

Capabilities
------------
• Parses absolute dates/times from text (dateutil)
• Uses the LLM to resolve relative temporal expressions
  ("the next morning", "shortly after", "two days later")
• Sorts events by normalised time
• Flags events where temporal ordering is ambiguous

Standalone usage
----------------
    from agents.timeline_reconstruction_agent import TimelineReconstructionAgent
    from config import get_llm
    agent = TimelineReconstructionAgent()
    timeline = agent.run(structured_facts, llm=get_llm("claude-sonnet-4-6", "anthropic"))
"""

from __future__ import annotations
from langchain_core.runnables import RunnableConfig
import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from core.state import TimelineEvent
from core.logger import audit, get_logger

logger = get_logger("timeline_reconstruction_agent")


# ---------------------------------------------------------------------------
# Pydantic schema for LLM structured output
# ---------------------------------------------------------------------------

class TimelineEventModel(BaseModel):
    event_id: str = Field(description="Same event_id as in structured_facts input")
    description: str = Field(description="One-sentence description")
    timestamp: Optional[str] = Field(None, description="Original timestamp from transcript")
    normalized_time: Optional[str] = Field(
        None,
        description="ISO-8601 datetime (e.g. '2024-01-15T22:00:00') or "
                    "relative description if absolute time cannot be determined "
                    "(e.g. 'T+2h after E001', 'before E003')"
    )
    actors: list[str] = Field(default_factory=list)
    location: Optional[str] = Field(None)
    source_excerpt: str = Field(description="Verbatim quote supporting this event")
    temporal_confidence: str = Field(
        description="HIGH if absolute datetime known, MEDIUM if inferred, LOW if ambiguous"
    )


class TimelineModel(BaseModel):
    events: list[TimelineEventModel] = Field(description="All events sorted chronologically")
    anchor_date: Optional[str] = Field(
        None,
        description="The earliest definite date found in the transcript, used as reference point"
    )
    notes: str = Field(
        description="Brief note on any temporal gaps, ambiguities, or assumptions made"
    )


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a legal timeline analyst. Your task is to reconstruct a precise chronological timeline from structured legal events.

Instructions:
1. Assign a normalized_time to every event:
   - If an absolute date/time is present, use ISO-8601 format: YYYY-MM-DDTHH:MM:SS
   - If the time is relative ("the next morning", "two hours later"), express it as an offset from a known event: "T+1d after E002"
   - If the time is completely unknown, use null
2. Sort events in chronological order (earliest first). When relative order is known but absolute time is not, use relative markers.
3. For temporal_confidence: HIGH = explicit datetime, MEDIUM = inferred from context, LOW = unknown
4. Identify the anchor_date: the earliest definite date mentioned.
5. Note any temporal gaps or ambiguities in the notes field.

Do NOT invent timestamps. Only use information explicitly present in the events data.
Maintain legal neutrality — do not draw conclusions about guilt or innocence.
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class TimelineReconstructionAgent:
    """Organises structured events into a chronological timeline."""

    def run(self, structured_facts: dict, llm=None) -> dict:
        """
        Reconstruct timeline from structured facts.

        Args:
            structured_facts: output of TranscriptProcessingAgent.run()
            llm: LangChain chat model (optional; fallback sorts by appearance order)

        Returns:
            dict with 'timeline' (list[TimelineEvent]) and audit log entries
        """
        log_start = audit("timeline_reconstruction_agent", "start",
                          events_in=len(structured_facts.get("events", [])))

        events = structured_facts.get("events", [])
        if not events:
            log_end = audit("timeline_reconstruction_agent", "complete_empty")
            return {"timeline": [], "audit_log": [log_start, log_end]}

        if llm is not None:
            timeline = self._llm_reconstruct(events, llm)
        else:
            timeline = self._fallback_reconstruct(events)

        log_end = audit("timeline_reconstruction_agent", "complete",
                        events_out=len(timeline))
        return {"timeline": timeline, "audit_log": [log_start, log_end]}

    def _llm_reconstruct(self, events: list[dict], llm) -> list[TimelineEvent]:
        """Use LLM structured output to normalise and sort events."""
        try:
            structured_llm = llm.with_structured_output(TimelineModel)
            events_json = json.dumps(events, indent=2)
            result: TimelineModel = structured_llm.invoke([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Reconstruct the chronological timeline from these events:\n\n{events_json}"},
            ])
            return [
                TimelineEvent(
                    event_id=e.event_id,
                    description=e.description,
                    timestamp=e.timestamp,
                    normalized_time=e.normalized_time,
                    actors=e.actors,
                    location=e.location,
                    source_excerpt=e.source_excerpt,
                )
                for e in result.events
            ]
        except Exception as exc:
            logger.error("llm_timeline_failed", error=str(exc))
            return self._fallback_reconstruct(events)

    @staticmethod
    def _fallback_reconstruct(events: list[dict]) -> list[TimelineEvent]:
        """
        Fallback: attempt dateutil parsing; preserve input order when parsing fails.
        """
        parsed: list[tuple] = []
        for ev in events:
            ts = ev.get("timestamp") or ""
            normalized = _try_parse_date(ts)
            parsed.append((normalized, ev))

        # Sort: events with parsed dates first, then unknown order preserved
        parsed.sort(key=lambda x: (x[0] is None, x[0] or ""))

        timeline: list[TimelineEvent] = []
        for _, ev in parsed:
            timeline.append(TimelineEvent(
                event_id=ev.get("event_id", "E000"),
                description=ev.get("description", ""),
                timestamp=ev.get("timestamp"),
                normalized_time=_try_parse_date(ev.get("timestamp") or ""),
                actors=ev.get("actors", []),
                location=ev.get("location"),
                source_excerpt=ev.get("source_excerpt", "")[:200],
            ))
        return timeline


def _try_parse_date(text: str) -> Optional[str]:
    """Attempt to parse a date string with python-dateutil."""
    if not text:
        return None
    try:
        from dateutil import parser as duparser
        dt = duparser.parse(text, fuzzy=True)
        return dt.isoformat()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------

_agent_instance = TimelineReconstructionAgent()


def timeline_reconstruction_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
    """LangGraph node: timeline reconstruction."""
    if state.get("security_input_blocked"):
        return {"audit_log": [audit("timeline_reconstruction_agent", "skipped_blocked_input")]}

    llm = None
    if config:
        try:
            from config import get_llm_from_config
            llm = get_llm_from_config(config)
        except Exception as e:
            logger.warning("llm_init_failed", error=str(e))

    result = _agent_instance.run(state.get("structured_facts", {}), llm=llm)

    # Persist timeline to memory store
    run_id = state.get("run_id")
    if run_id:
        try:
            from core.memory import memory_store
            memory_store.save_timeline(run_id, result["timeline"])
        except Exception:
            pass

    from core.state import AgentStatus
    status_entry = AgentStatus(
        source_agent="timeline_reconstruction",
        status="complete",
        confidence="HIGH" if llm is not None else "MEDIUM",
        next_action="proceed_to_consistency_analysis",
        notes=f"{len(result['timeline'])} events placed on timeline",
    )

    return {
        "timeline": result["timeline"],
        "audit_log": result["audit_log"],
        "agent_statuses": {
            **state.get("agent_statuses", {}),
            "timeline_reconstruction": status_entry,
        },
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, json
    sample_facts = {
        "events": [
            {"event_id": "E001", "description": "Defendant seen at Changi Airport",
             "timestamp": "9:45pm on 15 January 2024", "actors": ["John Tan"], "location": "Changi Airport",
             "source_excerpt": "witness stated he was at Changi Airport at 9:45pm"},
            {"event_id": "E002", "description": "Plaintiff saw defendant at crime scene",
             "timestamp": "10pm on 15 January 2024", "actors": ["plaintiff", "John Tan"],
             "location": "scene", "source_excerpt": "she saw him at the scene at 10pm"},
            {"event_id": "E003", "description": "Court hearing begins",
             "timestamp": "15 January 2024", "actors": ["Justice Lee"], "location": "High Court",
             "source_excerpt": "appeared before Justice Lee at the High Court"},
        ],
        "key_statements": [],
        "summary": "Legal proceedings involving John Tan",
    }
    agent = TimelineReconstructionAgent()
    result = agent.run(sample_facts)
    print(json.dumps(result, indent=2, default=str))
