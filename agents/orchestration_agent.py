"""
TRUTHFORGE AI — Orchestration Agent
================================================================
Coordinates the full multi-agent pipeline using LangGraph.

Pipeline sequence:
  START
    → security_input          (ResponsibleAISecurityAgent — input gate)
    → transcript_processing   (TranscriptProcessingAgent)
    → timeline_reconstruction (TimelineReconstructionAgent)
    → consistency_analysis    (ConsistencyAnalysisAgent)
    ↓  [conditional] requires_review=True OR low-confidence inconsistencies?
    → consistency_analysis    (second pass — re-invoked with hint)
    → explainability          (ExplainabilityAgent)
    → security_output         (ResponsibleAISecurityAgent — output gate)
  END

Autonomy enhancements (v1.1)
-----------------------------
• Complexity routing: transcripts > 5000 chars are tagged COMPLEX and
  given a second-pass analysis automatically
• Second-pass review: if any inconsistency has LOW confidence, the
  orchestrator re-invokes consistency_analysis with a "uncertain_review"
  hint so the LLM focuses on ambiguous findings
• requires_review flag: agents can set this to signal that the
  orchestrator should trigger additional scrutiny

Features
--------
• Conditional edge: if security_input_blocked → skip to END immediately
• Each node appends to audit_log (operator.add, never overwrites)
• InMemorySaver checkpointer — each Streamlit session gets a unique thread_id
• run_pipeline() integrates run_metadata tracking and metrics recording
• run_pipeline() is the main public API
"""

from __future__ import annotations
import time
from typing import Literal

from core.state import TruthForgeState, empty_state, AgentStatus
from core.memory import build_checkpointer, new_thread_id
from core.logger import audit, get_logger
from core.metrics import metrics as _metrics
import core.run_metadata as _run_meta

logger = get_logger("orchestration_agent")

# Transcript length threshold above which COMPLEX routing applies
_COMPLEX_THRESHOLD_CHARS = 5000
# Second-pass is triggered when this fraction of inconsistencies are LOW confidence
_SECOND_PASS_LOW_CONF_THRESHOLD = 0.5

# Import node functions from each agent
from agents.responsible_ai_security_agent import security_input_node, security_output_node
from agents.transcript_processing_agent import transcript_processing_node
from agents.timeline_reconstruction_agent import timeline_reconstruction_node
from agents.consistency_analysis_agent import consistency_analysis_node
from agents.explainability_agent import explainability_node

# ---------------------------------------------------------------------------
# Routing function for conditional edge after security_input
# ---------------------------------------------------------------------------

def _route_after_security(state: TruthForgeState) -> Literal["transcript_processing", "__end__"]:
    """If input was blocked by security, route directly to END."""
    if state.get("security_input_blocked"):
        logger.warning("pipeline_halted_blocked_input")
        return "__end__"
    return "transcript_processing"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

_GRAPH = None
_CHECKPOINTER = None


def _build_graph():
    """Build and compile the LangGraph StateGraph."""
    from langgraph.graph import StateGraph, START, END

    builder = StateGraph(TruthForgeState)

    # Register nodes
    builder.add_node("security_input",           security_input_node)
    builder.add_node("transcript_processing",    transcript_processing_node)
    builder.add_node("timeline_reconstruction",  timeline_reconstruction_node)
    builder.add_node("consistency_analysis",     consistency_analysis_node)
    builder.add_node("explainability",           explainability_node)
    builder.add_node("security_output",          security_output_node)

    # Edges
    builder.add_edge(START, "security_input")
    builder.add_conditional_edges(
        "security_input",
        _route_after_security,
        {
            "transcript_processing": "transcript_processing",
            "__end__": END,
        },
    )
    builder.add_edge("transcript_processing",   "timeline_reconstruction")
    builder.add_edge("timeline_reconstruction", "consistency_analysis")
    builder.add_edge("consistency_analysis",    "explainability")
    builder.add_edge("explainability",          "security_output")
    builder.add_edge("security_output",         END)

    checkpointer = build_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)
    return graph, checkpointer


def _get_graph():
    """Lazily build and cache the compiled graph."""
    global _GRAPH, _CHECKPOINTER
    if _GRAPH is None:
        _GRAPH, _CHECKPOINTER = _build_graph()
    return _GRAPH


# ---------------------------------------------------------------------------
# Autonomy helpers
# ---------------------------------------------------------------------------

def _assess_complexity(transcript: str) -> str:
    """Classify transcript complexity to route pipeline strategy."""
    if len(transcript) > _COMPLEX_THRESHOLD_CHARS:
        return "COMPLEX"
    return "STANDARD"


def _needs_second_pass(state: TruthForgeState) -> bool:
    """
    Determine if a second-pass consistency analysis is warranted.

    Triggers when:
    1. state.requires_review is True (set by an agent)
    2. Complexity is COMPLEX (long transcript)
    3. More than half of inconsistencies have LOW confidence explanations
    """
    if state.get("requires_review"):
        return True
    if state.get("complexity_level") == "COMPLEX":
        return True
    # Check if explanations have low confidence
    explanations = state.get("explanations", [])
    if explanations:
        low_conf = sum(1 for e in explanations if e.get("confidence") == "LOW")
        if low_conf / len(explanations) >= _SECOND_PASS_LOW_CONF_THRESHOLD:
            return True
    return False


def _run_second_pass(
    state: TruthForgeState,
    config: dict,
) -> TruthForgeState:
    """
    Re-invoke consistency_analysis with a second-pass hint injected
    into the config. Updates state.inconsistencies in-place copy.
    """
    logger.info("second_pass_triggered", reason="requires_review or low_confidence")
    log = audit("orchestration_agent", "second_pass_start",
                current_inconsistencies=len(state.get("inconsistencies", [])))

    # Signal to the consistency agent that this is a review pass
    second_config = dict(config)
    second_config.setdefault("configurable", {})
    second_config["configurable"]["second_pass"] = True
    second_config["configurable"]["uncertain_review"] = True

    try:
        result = consistency_analysis_node(state, config=second_config)
        refined = result.get("inconsistencies", state.get("inconsistencies", []))
        log2 = audit("orchestration_agent", "second_pass_complete",
                     refined_inconsistencies=len(refined))
        return {
            **state,
            "inconsistencies": refined,
            "audit_log": state.get("audit_log", []) + [log, log2],
            "agent_statuses": {
                **state.get("agent_statuses", {}),
                "consistency_analysis_second_pass": AgentStatus(
                    source_agent="consistency_analysis",
                    status="second_pass",
                    confidence="HIGH",
                    next_action="proceed_to_explainability",
                    notes=f"Second pass refined to {len(refined)} inconsistencies",
                ),
            },
        }
    except Exception as exc:
        logger.warning("second_pass_failed", error=str(exc))
        return state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    transcript: str,
    llm_config: dict | None = None,
    thread_id: str | None = None,
) -> TruthForgeState:
    """
    Run the full TRUTHFORGE AI pipeline on a transcript.

    Args:
        transcript: raw legal transcript text
        llm_config: LangGraph config dict, e.g.
                    {"configurable": {"model": "claude-sonnet-4-6", "model_provider": "anthropic"}}
                    If None, agents run in fallback (spaCy-only / rule-based) mode.
        thread_id: unique session ID for checkpointing (auto-generated if None)

    Returns:
        Final TruthForgeState dict
    """
    graph = _get_graph()
    tid = thread_id or new_thread_id()
    start_time = time.perf_counter()

    # --- Open run metadata record ---
    run_id = _run_meta.open_run(transcript, llm_config, tid)

    # --- Complexity assessment (autonomy routing) ---
    complexity = _assess_complexity(transcript)

    initial_state = empty_state(raw_transcript=transcript)
    initial_state["complexity_level"] = complexity
    initial_state["run_id"] = run_id
    initial_state["audit_log"] = [
        audit("orchestration_agent", "pipeline_start",
              thread_id=tid, chars=len(transcript), complexity=complexity)
    ]

    config = llm_config or {}
    config.setdefault("configurable", {})
    config["configurable"]["thread_id"] = tid

    second_pass_triggered = False

    try:
        final_state = graph.invoke(initial_state, config=config)

        # --- Autonomy: second-pass analysis if warranted ---
        if _needs_second_pass(final_state):
            final_state = _run_second_pass(final_state, config)
            second_pass_triggered = True

        final_state["audit_log"] = final_state.get("audit_log", []) + [
            audit("orchestration_agent", "pipeline_complete",
                  thread_id=tid, second_pass=second_pass_triggered)
        ]

    except Exception as exc:
        logger.error("pipeline_error", error=str(exc), thread_id=tid)
        final_state = initial_state
        final_state["error_state"] = f"Pipeline error: {exc}"
        final_state["final_report"] = (
            "An error occurred during pipeline execution. "
            "Please check the audit log for details."
        )

    # --- Record metrics ---
    duration_ms = (time.perf_counter() - start_time) * 1000
    blocked = final_state.get("security_input_blocked", False)
    error = final_state.get("error_state")
    cfg = (llm_config or {}).get("configurable", {})
    _metrics.record_run(
        duration_ms=duration_ms,
        success=(error is None and not blocked),
        blocked=blocked,
        second_pass=second_pass_triggered,
        model_name=cfg.get("model", "fallback"),
        n_inconsistencies=len(final_state.get("inconsistencies", [])),
    )

    # --- Close run metadata record ---
    _run_meta.close_run(run_id, final_state, duration_ms)

    return final_state


def stream_pipeline(
    transcript: str,
    llm_config: dict | None = None,
    thread_id: str | None = None,
):
    """
    Generator that yields (node_name, partial_state) tuples as the pipeline executes.
    Useful for Streamlit live progress updates.
    """
    graph = _get_graph()
    tid = thread_id or new_thread_id()
    complexity = _assess_complexity(transcript)
    run_id = _run_meta.open_run(transcript, llm_config, tid)
    start_time = time.perf_counter()

    initial_state = empty_state(raw_transcript=transcript)
    initial_state["complexity_level"] = complexity
    initial_state["run_id"] = run_id
    initial_state["audit_log"] = [
        audit("orchestration_agent", "stream_start",
              thread_id=tid, complexity=complexity)
    ]
    config = llm_config or {}
    config.setdefault("configurable", {})
    config["configurable"]["thread_id"] = tid

    final_state: dict = {}

    try:
        for chunk in graph.stream(
            initial_state,
            config=config,
            stream_mode="updates",
        ):
            if isinstance(chunk, dict):
                for node_name, state_update in chunk.items():
                    final_state.update(state_update)
                    yield node_name, state_update
            else:
                node_name, state_update = chunk[0], chunk[1]
                final_state.update(state_update)
                yield node_name, state_update

        # Autonomy second pass (post-stream)
        if final_state and _needs_second_pass(final_state):
            refined = _run_second_pass(final_state, config)
            final_state.update(refined)
            yield "consistency_analysis_second_pass", {
                "inconsistencies": refined.get("inconsistencies", []),
                "audit_log": [audit("orchestration_agent", "second_pass_yielded")],
            }

    except Exception as exc:
        logger.error("pipeline_stream_error", error=str(exc))
        yield "error", {"error_state": str(exc)}
        final_state["error_state"] = str(exc)

    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        blocked = final_state.get("security_input_blocked", False)
        error = final_state.get("error_state")
        cfg = (llm_config or {}).get("configurable", {})
        _metrics.record_run(
            duration_ms=duration_ms,
            success=(error is None and not blocked),
            blocked=blocked,
            model_name=cfg.get("model", "fallback"),
        )
        _run_meta.close_run(run_id, final_state, duration_ms)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, json

    DEMO_TRANSCRIPT = """
    COURT HEARING TRANSCRIPT — CASE NO. HC/S 1234/2024
    Date: 15 January 2024
    Before: Justice Lee Hwee Lian, High Court of Singapore

    EXAMINATION OF PW1 (First Prosecution Witness — Ms. Sarah Lim):
    Counsel: Can you describe what you saw on the night of 14 January 2024?
    PW1: Yes. I clearly saw the defendant, Mr. John Tan, at the carpark of Blk 45 at 10:30pm.

    CROSS-EXAMINATION OF PW1:
    Defence: At 10:30pm, where exactly were you standing?
    PW1: I was at the void deck of Blk 44, directly across the road.

    EXAMINATION OF DW1 (First Defence Witness — Mr. Ahmad bin Salleh):
    Counsel: Where was Mr. John Tan on the evening of 14 January 2024?
    DW1: He was with me at Changi Airport Terminal 3, collecting my friend from the airport.
    Counsel: What time did you arrive at the airport?
    DW1: We arrived at about 9:45pm and left around 11:15pm.

    EXAMINATION OF DW2 (Second Defence Witness — Departure Records):
    The defence tendered flight arrival records showing that the flight from Bangkok arrived at Changi Airport at 9:52pm on 14 January 2024.
    """.strip()

    print("Running TRUTHFORGE AI pipeline in fallback mode (no LLM)...\n")
    result = run_pipeline(DEMO_TRANSCRIPT, llm_config=None)
    print("=== FINAL REPORT ===")
    print(result.get("final_report", "No report generated."))
    print("\n=== INCONSISTENCIES ===")
    print(json.dumps(result.get("inconsistencies", []), indent=2, default=str))
    print("\n=== COMPLEXITY ===")
    print(result.get("complexity_level"))
    print("\n=== AUDIT LOG ===")
    for entry in result.get("audit_log", []):
        print(entry)
