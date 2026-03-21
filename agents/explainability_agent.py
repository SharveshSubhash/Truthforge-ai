"""
TRUTHFORGE AI — Explainability Agent
================================================================
Converts raw Inconsistency records into clear, human-readable
explanations for legal professionals.

For each inconsistency the agent:
  1. Observes: identifies the exact transcript excerpts involved
  2. Reasons: determines the nature and significance of the conflict
  3. Explains: writes a plain-English explanation with direct evidence links
  4. Recommends: suggests follow-up questions or actions

Uses ReAct-style prompting (observe → reason → explain).

Standalone usage
----------------
    from agents.explainability_agent import ExplainabilityAgent
    from config import get_llm
    agent = ExplainabilityAgent()
    result = agent.run(inconsistencies, raw_transcript, llm=get_llm(...))
"""

from __future__ import annotations
from langchain_core.runnables import RunnableConfig
import json
from typing import Optional

from pydantic import BaseModel, Field

from core.state import ExplanationEntry
from core.logger import audit, get_logger

logger = get_logger("explainability_agent")


# ---------------------------------------------------------------------------
# Pydantic schema for LLM structured output
# ---------------------------------------------------------------------------

class ExplanationModel(BaseModel):
    inconsistency_id: str = Field(description="Must match the input inconsistency_id")
    plain_english: str = Field(
        description="Clear explanation of the inconsistency for a legal professional "
                    "(2–4 sentences). No legal conclusions about guilt/innocence."
    )
    evidence_quotes: list[str] = Field(
        description="1–3 verbatim quotes from the transcript that are directly relevant. "
                    "Each quote max 150 characters."
    )
    confidence: str = Field(
        description="Your confidence in this analysis: HIGH, MEDIUM, or LOW"
    )
    recommendation: str = Field(
        description="One suggested follow-up action for the legal team "
                    "(e.g., 'Request clarification from witness on their location at 9:45pm')"
    )


class ExplanationsModel(BaseModel):
    explanations: list[ExplanationModel]
    overall_summary: str = Field(
        description="2–3 sentence summary of the overall consistency of the transcript. "
                    "Must be neutral — no legal conclusions."
    )


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

PROMPT_VERSION = "v1.1"  # Bump when prompt changes (for run_metadata traceability)

_SYSTEM_PROMPT = """You are a legal explainability analyst. Your role is to generate clear, transparent explanations for detected inconsistencies in legal transcripts.

For each inconsistency you will:
1. OBSERVE: Identify the exact statements that conflict.
2. REASON: Determine the nature of the conflict (timing, location, attribution, etc.).
3. EXPLAIN: Write a plain-English explanation that a legal professional (not a computer scientist) can understand.
4. RECOMMEND: Suggest one concrete follow-up action for the legal team.

Output requirements:
- Use simple, professional language (no technical jargon).
- Provide verbatim quotes from the transcript as evidence.
- Do NOT speculate about motivations or draw legal conclusions.
- Do NOT state that any party is guilty, innocent, lying, or telling the truth.
- Confidence should reflect how clear-cut the inconsistency is (HIGH = obvious contradiction, LOW = ambiguous).
- The overall_summary must be factually neutral.

FAIRNESS AND NEUTRALITY RULES (mandatory):
- Do NOT make or imply credibility judgements based on a person's name, race, ethnicity, gender, religion, nationality, socioeconomic status, accent, or any other identity characteristic.
- Do NOT use phrases such as "people like him tend to", "given her background", "as a foreigner", or any similar generalisation tied to identity.
- Do NOT use language that pre-judges guilt or innocence: forbidden phrases include "clearly lying", "obviously fabricated", "must be true because", "hard to believe".
- If an inconsistency involves a person's identity or background, describe ONLY the factual conflict (e.g. "Statement A places the witness at location X while Statement B places them at location Y") without attributing it to their identity.
- Treat all parties — prosecution, defence, witnesses — with equal analytical rigour. Apply the same standard of scrutiny regardless of which side a statement comes from.
- Use neutral descriptors: "the witness", "the accused", "the complainant" — not "the victim" (which implies a conclusion) or "the perpetrator" (which implies guilt).
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class ExplainabilityAgent:
    """Generates human-readable explanations for detected inconsistencies."""

    def run(
        self,
        inconsistencies: list,
        raw_transcript: str,
        llm=None,
    ) -> dict:
        """
        Generate explanations for all inconsistencies.

        Args:
            inconsistencies: list of Inconsistency dicts from ConsistencyAnalysisAgent
            raw_transcript: original full transcript text (for quote verification)
            llm: LangChain chat model

        Returns:
            dict with 'explanations' and audit log entries
        """
        log_start = audit("explainability_agent", "start",
                          inconsistencies_in=len(inconsistencies))

        if not inconsistencies:
            summary_entry = ExplanationEntry(
                inconsistency_id="NONE",
                plain_english="No inconsistencies were detected in this transcript.",
                evidence_quotes=[],
                confidence="HIGH",
                recommendation="No follow-up required based on this analysis.",
            )
            log_end = audit("explainability_agent", "complete_no_inconsistencies")
            return {
                "explanations": [summary_entry],
                "final_report": _build_clean_report([], "No inconsistencies detected."),
                "audit_log": [log_start, log_end],
            }

        if llm is not None:
            explanations, overall_summary = self._llm_explain(
                inconsistencies, raw_transcript, llm
            )
        else:
            explanations, overall_summary = self._fallback_explain(inconsistencies)

        final_report = _build_clean_report(explanations, overall_summary)
        log_end = audit("explainability_agent", "complete",
                        explanations_out=len(explanations))
        return {
            "explanations": explanations,
            "final_report": final_report,
            "audit_log": [log_start, log_end],
        }

    def _llm_explain(
        self,
        inconsistencies: list,
        raw_transcript: str,
        llm,
    ) -> tuple[list[ExplanationEntry], str]:
        """LLM-powered explanation generation."""
        try:
            structured_llm = llm.with_structured_output(ExplanationsModel)
            # Trim transcript to avoid token limits
            transcript_preview = raw_transcript[:3000] + (
                "\n[... transcript truncated for brevity ...]" if len(raw_transcript) > 3000 else ""
            )
            result: ExplanationsModel = structured_llm.invoke([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Generate explanations for these inconsistencies.\n\n"
                    f"INCONSISTENCIES:\n{json.dumps(inconsistencies, indent=2, default=str)}\n\n"
                    f"ORIGINAL TRANSCRIPT (for quote verification):\n{transcript_preview}"
                )},
            ])
            entries = [
                ExplanationEntry(
                    inconsistency_id=e.inconsistency_id,
                    plain_english=e.plain_english,
                    evidence_quotes=e.evidence_quotes,
                    confidence=e.confidence,
                    recommendation=e.recommendation,
                )
                for e in result.explanations
            ]
            return entries, result.overall_summary
        except Exception as exc:
            logger.error("llm_explain_failed", error=str(exc))
            return self._fallback_explain(inconsistencies)

    @staticmethod
    def _fallback_explain(
        inconsistencies: list,
    ) -> tuple[list[ExplanationEntry], str]:
        """Rule-based fallback explanation generator."""
        entries: list[ExplanationEntry] = []
        for inc in inconsistencies:
            itype = inc.get("type", "OTHER")
            sev = inc.get("severity", "MEDIUM")
            entries.append(ExplanationEntry(
                inconsistency_id=inc.get("inconsistency_id", "INC?"),
                plain_english=(
                    f"A {itype.replace('_', ' ').lower()} was detected ({sev} severity). "
                    f"{inc.get('explanation', 'Two statements appear to contradict each other.')}"
                ),
                evidence_quotes=[
                    inc.get("statement_a", "")[:150],
                    inc.get("statement_b", "")[:150],
                ],
                confidence="MEDIUM",
                recommendation="Review the relevant portions of the transcript with the parties involved.",
            ))
        overall = (
            f"{len(inconsistencies)} inconsistency/ies detected. "
            "Legal professionals should review the flagged sections for further clarification."
        )
        return entries, overall


def _build_clean_report(
    explanations: list[ExplanationEntry],
    overall_summary: str,
) -> str:
    """Build the markdown final report from explanations."""
    lines = [
        "# TRUTHFORGE AI — Consistency Analysis Report",
        "",
        "## Overall Summary",
        overall_summary,
        "",
        "---",
        "",
        f"## Detected Inconsistencies ({len(explanations)} total)",
        "",
    ]
    for exp in explanations:
        lines += [
            f"### {exp['inconsistency_id']}",
            "",
            f"**Explanation:** {exp['plain_english']}",
            "",
            "**Evidence from Transcript:**",
        ]
        for q in exp.get("evidence_quotes", []):
            if q:
                lines.append(f'> "{q}"')
        lines += [
            "",
            f"**Confidence:** {exp['confidence']}",
            f"**Recommended Action:** {exp['recommendation']}",
            "",
            "---",
            "",
        ]
    lines.append(
        "*This report is generated by TRUTHFORGE AI as an analytical aid. "
        "It does not constitute legal advice or determinations of guilt or innocence. "
        "Human legal professionals retain full responsibility for all legal interpretations.*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------

_agent_instance = ExplainabilityAgent()


def explainability_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
    """LangGraph node: explanation generation."""
    if state.get("security_input_blocked"):
        return {"audit_log": [audit("explainability_agent", "skipped_blocked_input")]}

    llm = None
    if config:
        try:
            from config import get_llm_from_config
            llm = get_llm_from_config(config)
        except Exception as e:
            logger.warning("llm_init_failed", error=str(e))

    result = _agent_instance.run(
        inconsistencies=state.get("inconsistencies", []),
        raw_transcript=state.get("raw_transcript", ""),
        llm=llm,
    )

    # Save run summary to persistent memory
    run_id = state.get("run_id")
    if run_id:
        try:
            from core.memory import memory_store
            from config import DEFAULT_MODEL_NAME
            cfg = (config or {})
            model = cfg.get("configurable", {}).get("model", DEFAULT_MODEL_NAME) if cfg else DEFAULT_MODEL_NAME
            memory_store.save_summary(run_id, {
                "n_inconsistencies": len(state.get("inconsistencies", [])),
                "n_entities": len(state.get("entities", [])),
                "transcript_chars": len(state.get("raw_transcript", "")),
                "model_name": model,
                "prompt_version": PROMPT_VERSION,
            })
        except Exception:
            pass

    from core.state import AgentStatus
    n_expl = len(result["explanations"])
    status_entry = AgentStatus(
        source_agent="explainability",
        status="complete",
        confidence="HIGH" if llm is not None else "MEDIUM",
        next_action="proceed_to_security_output",
        notes=f"{n_expl} explanation(s) generated",
    )

    return {
        "explanations": result["explanations"],
        "final_report": result["final_report"],
        "audit_log": result["audit_log"],
        "agent_statuses": {
            **state.get("agent_statuses", {}),
            "explainability": status_entry,
        },
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, json
    sample_inconsistencies = [
        {
            "inconsistency_id": "INC001",
            "type": "LOCATION_CONFLICT",
            "statement_a": "witness stated he was at Changi Airport at 9:45pm",
            "statement_b": "she saw him at the scene at 10pm",
            "event_a_id": "E001",
            "event_b_id": "E002",
            "severity": "HIGH",
            "explanation": "Two events place the defendant in different locations within 15 minutes.",
        }
    ]
    sample_transcript = (
        "The defendant John Tan appeared before Justice Lee. "
        "A witness stated he was at Changi Airport at 9:45pm on 15 January 2024. "
        "However, the plaintiff testified that she saw him at the scene at 10pm on the same date."
    )
    agent = ExplainabilityAgent()
    result = agent.run(sample_inconsistencies, sample_transcript)
    print(json.dumps(result, indent=2, default=str))
    print("\n=== FINAL REPORT ===")
    print(result.get("final_report", ""))
