"""
TRUTHFORGE AI — Shared Pipeline State
All agents read from and write to this TypedDict. The audit_log field uses
operator.add so every agent can safely append without overwriting other agents' entries.

v1.1 additions (inter-agent communication improvements):
  - AgentStatus: standardised per-agent handoff record
  - TruthForgeState.agent_statuses: dict of agent → AgentStatus
  - TruthForgeState.requires_review: flag for autonomy second-pass logic
  - TruthForgeState.complexity_level: routing hint set by orchestration agent
  - TruthForgeState.run_id: links to artifacts/runs/ metadata file
"""

from __future__ import annotations
from typing import TypedDict, Annotated, Optional
import operator


class Entity(TypedDict):
    """A named entity extracted from the transcript."""
    text: str
    label: str        # PERSON, JUDGE, COURT, STATUTE, CASE_CITATION, DATE, LOCATION, etc.
    start: int        # character offset in sanitized_transcript
    end: int
    confidence: float


class TimelineEvent(TypedDict):
    """A single event placed on the reconstructed timeline."""
    event_id: str
    description: str
    timestamp: Optional[str]          # raw timestamp from transcript
    normalized_time: Optional[str]    # ISO-8601 or relative description
    actors: list[str]                 # names / roles involved
    location: Optional[str]
    source_excerpt: str               # verbatim quote from transcript


class Inconsistency(TypedDict):
    """A detected logical inconsistency between two statements."""
    inconsistency_id: str
    type: str                # DATE_MISMATCH | LOCATION_CONFLICT | ACTOR_CONFLICT | TEMPORAL_ORDER | OTHER
    statement_a: str         # first conflicting statement (verbatim)
    statement_b: str         # second conflicting statement (verbatim)
    event_a_id: Optional[str]
    event_b_id: Optional[str]
    severity: str            # LOW | MEDIUM | HIGH
    explanation: str         # brief machine-generated note


class ExplanationEntry(TypedDict):
    """Human-readable explanation for a single inconsistency."""
    inconsistency_id: str
    plain_english: str       # clear explanation for legal professional
    evidence_quotes: list[str]   # verbatim excerpts from transcript
    confidence: str          # LOW | MEDIUM | HIGH
    recommendation: str      # suggested follow-up action


class AgentStatus(TypedDict):
    """
    Standardised inter-agent handoff record written by each node.
    Provides structured visibility into what each agent did and
    what the next agent should expect.
    """
    source_agent: str        # name of the agent that wrote this record
    status: str              # complete | error | skipped | second_pass
    confidence: str          # HIGH | MEDIUM | LOW
    next_action: str         # hint for downstream agent or orchestrator
    notes: str               # brief free-text (optional)


class TruthForgeState(TypedDict):
    """
    Central pipeline state passed between all LangGraph nodes.
    Only append to audit_log using operator.add to avoid race conditions.
    """
    # --- Input ---
    raw_transcript: str

    # --- Security (input gate) ---
    sanitized_transcript: str
    security_input_flags: list[str]        # any injection signals detected
    security_input_blocked: bool           # True → pipeline halts

    # --- Transcript Processing ---
    entities: list[Entity]
    structured_facts: dict                 # {events: [...], key_statements: [...], summary: str}

    # --- Timeline ---
    timeline: list[TimelineEvent]

    # --- Consistency Analysis ---
    inconsistencies: list[Inconsistency]

    # --- Explainability ---
    explanations: list[ExplanationEntry]

    # --- Security (output gate) ---
    security_output_flags: list[str]
    final_report: str                      # filtered, safe report delivered to user

    # --- Inter-agent communication (v1.1) ---
    agent_statuses: dict                   # {agent_name: AgentStatus}
    requires_review: bool                  # True → orchestrator triggers second-pass analysis
    complexity_level: str                  # SIMPLE | STANDARD | COMPLEX (set by orchestrator)

    # --- Traceability ---
    run_id: Optional[str]                  # links to artifacts/runs/<run_id>.json

    # --- Cross-cutting concerns ---
    audit_log: Annotated[list[str], operator.add]   # append-only, all agents write here
    error_state: Optional[str]                       # set if a node fails


def empty_state(raw_transcript: str = "") -> TruthForgeState:
    """Return a fresh, fully-initialised pipeline state."""
    return TruthForgeState(
        raw_transcript=raw_transcript,
        sanitized_transcript="",
        security_input_flags=[],
        security_input_blocked=False,
        entities=[],
        structured_facts={},
        timeline=[],
        inconsistencies=[],
        explanations=[],
        security_output_flags=[],
        final_report="",
        agent_statuses={},
        requires_review=False,
        complexity_level="STANDARD",
        run_id=None,
        audit_log=[],
        error_state=None,
    )
