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

Uses ReAct-style prompting (observe → reason → explain → recommend).
Each step is captured as a separate structured field so the reasoning
chain is auditable and explainable to legal professionals.

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
# Agent-specific threat model
# ---------------------------------------------------------------------------
# 1. HALLUCINATED QUOTES   — LLM may fabricate evidence_quotes not present in
#                            the source transcript. Mitigation: _verify_quotes()
#                            checks each quote's prefix against the raw transcript
#                            before including it in the final report.
# 2. BIASED WORDING        — LLM may produce identity-based language despite
#                            fairness rules in the system prompt. Mitigation:
#                            _check_output_bias() scans plain_english and
#                            recommendation against _UNSAFE_PHRASES after
#                            generation; violations are logged to the audit trail.
# 3. OVERCLAIMING          — Explanations may drift into legal conclusions
#                            (guilt, innocence, credibility). Mitigation: system
#                            prompt explicitly forbids such language; fallback
#                            path generates deterministic neutral text only.
# 4. PROMPT INJECTION      — Malicious content in statement_a/statement_b fields
#                            passed from ConsistencyAnalysisAgent could attempt
#                            to manipulate LLM output. Mitigation: fields are
#                            JSON-serialised before inclusion in the user message,
#                            providing structural isolation.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pydantic schema for LLM structured output
# ---------------------------------------------------------------------------

class ExplanationModel(BaseModel):
    inconsistency_id: str = Field(description="Must match the input inconsistency_id")
    observe: str = Field(
        description="Step 1 — OBSERVE: Identify the exact conflicting statements from the transcript. "
                    "Quote them directly. One or two sentences only."
    )
    reason: str = Field(
        description="Step 2 — REASON: Determine the nature of the conflict (timing, location, "
                    "attribution, evolving account, etc.). One or two sentences only."
    )
    plain_english: str = Field(
        description="Step 3 — EXPLAIN: Clear explanation of the inconsistency for a legal professional "
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
        description="Step 4 — RECOMMEND: One suggested follow-up action for the legal team "
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

# ---------------------------------------------------------------------------
# Post-generation bias scanner — forbidden phrases that must not appear in
# LLM-generated explanation text.  Mirrors the system-prompt fairness rules
# so violations are caught in code, not only by prompt guidance.
# ---------------------------------------------------------------------------
import re as _re

_UNSAFE_PHRASES = _re.compile(
    r'\b(?:clearly lying|obviously fabricated|must be (?:true|false)|'
    r'hard to believe|people like \w+ tend to|given (?:his|her|their) background|'
    r'as a foreigner|is guilty|is innocent|the perpetrator|the victim|'
    r'obviously guilty|obviously innocent|must have lied)\b',
    _re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Confidence rubric — defines what HIGH / MEDIUM / LOW mean in code so that
# confidence values are auditable and not left to LLM discretion alone.
# ---------------------------------------------------------------------------
CONFIDENCE_RUBRIC: dict[str, str] = {
    "HIGH": (
        "The conflicting statements are verbatim contradictions with no plausible "
        "reconciliation given the transcript context."
    ),
    "MEDIUM": (
        "The conflict is notable but may have an alternative explanation, "
        "or involves imprecise recollection rather than deliberate contradiction."
    ),
    "LOW": (
        "The discrepancy is minor or involves estimates that could reasonably differ "
        "without indicating deception or material inconsistency."
    ),
}

_SYSTEM_PROMPT = """You are a legal explainability analyst. Your role is to generate clear, transparent explanations for detected inconsistencies in legal transcripts.

For each inconsistency you will follow the ReAct reasoning framework with four explicit steps:
1. OBSERVE  (observe field):   Identify the exact statements that conflict — quote them directly.
2. REASON   (reason field):    Determine the nature of the conflict (timing, location, attribution, evolving account, etc.).
3. EXPLAIN  (plain_english):   Write a plain-English explanation a legal professional can understand (2–4 sentences).
4. RECOMMEND (recommendation): Suggest one concrete follow-up action for the legal team.

Each step must be populated as a separate field in your output. This separation makes the reasoning chain auditable.

Output requirements:
- Use simple, professional language (no technical jargon).
- Provide verbatim quotes from the transcript as evidence (evidence_quotes field).
- Do NOT speculate about motivations or draw legal conclusions.
- Do NOT state that any party is guilty, innocent, lying, or telling the truth.
- Confidence must follow this rubric (HIGH / MEDIUM / LOW):
    HIGH   = verbatim contradiction with no plausible reconciliation.
    MEDIUM = notable conflict but an alternative explanation is possible.
    LOW    = minor discrepancy or estimate difference — not necessarily deceptive.
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
                          inconsistencies_in=len(inconsistencies),
                          prompt_version=PROMPT_VERSION)

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

        bias_audit: list[str] = []
        if llm is not None:
            explanations, overall_summary = self._llm_explain(
                inconsistencies, raw_transcript, llm
            )
            # Code-level bias enforcement: scan LLM output for unsafe phrases
            bias_audit = self._check_output_bias(explanations)
        else:
            explanations, overall_summary = self._fallback_explain(inconsistencies)

        final_report = _build_clean_report(explanations, overall_summary)
        log_end = audit("explainability_agent", "complete",
                        explanations_out=len(explanations),
                        bias_flags=len(bias_audit))
        return {
            "explanations": explanations,
            "final_report": final_report,
            "audit_log": [log_start] + bias_audit + [log_end],
        }

    def _llm_explain(
        self,
        inconsistencies: list,
        raw_transcript: str,
        llm,
    ) -> tuple[list[ExplanationEntry], str]:
        """LLM-powered explanation generation with ReAct reasoning chain logging."""
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
            entries = []
            for e in result.explanations:
                # Log each ReAct reasoning chain step for auditability
                logger.info(
                    "react_reasoning_chain",
                    inconsistency_id=e.inconsistency_id,
                    observe=e.observe,
                    reason=e.reason,
                    confidence=e.confidence,
                )
                verified_quotes = self._verify_quotes(e.evidence_quotes, raw_transcript)
                # Look up provenance fields set by the consistency agent
                source_inc = next(
                    (i for i in inconsistencies
                     if i.get("inconsistency_id") == e.inconsistency_id),
                    {},
                )
                entry = ExplanationEntry(
                    inconsistency_id=e.inconsistency_id,
                    plain_english=e.plain_english,
                    evidence_quotes=verified_quotes,
                    confidence=e.confidence,
                    recommendation=e.recommendation,
                )
                entry["detection_method"] = source_inc.get("detection_method", "llm")
                entry["source_confidence"] = source_inc.get("confidence", e.confidence)
                entries.append(entry)
            return entries, result.overall_summary
        except Exception as exc:
            logger.error("llm_explain_failed", error=str(exc))
            return self._fallback_explain(inconsistencies)

    @staticmethod
    def _check_output_bias(entries: list) -> list[str]:
        """
        Post-generation bias scan on LLM-generated explanation text.

        Scans plain_english and recommendation fields for phrases that violate
        the fairness rules enforced in the system prompt. Provides code-level
        enforcement rather than relying on prompt guidance alone.

        Returns a list of audit log entries for any violations found.
        Does NOT suppress output — violations are flagged and logged so human
        reviewers can make the final call.
        """
        audit_entries: list[str] = []
        for entry in entries:
            for field in ("plain_english", "recommendation"):
                text = entry.get(field, "")
                match = _UNSAFE_PHRASES.search(text)
                if match:
                    logger.warning(
                        "output_bias_detected | field=%s phrase=%r id=%s",
                        field, match.group(0), entry.get("inconsistency_id", "?"),
                    )
                    audit_entries.append(
                        audit("explainability_agent", "bias_phrase_detected",
                              field=field, phrase=match.group(0),
                              inconsistency_id=entry.get("inconsistency_id", "?"))
                    )
        return audit_entries

    @staticmethod
    def _verify_quotes(quotes: list[str], transcript: str) -> list[str]:
        """
        Remove quotes that cannot be found in the source transcript.
        Prevents LLM-hallucinated evidence from appearing in the report.
        Falls back to the first original quote if all fail verification.
        """
        verified = [q for q in quotes if q and q[:40].strip() in transcript]
        if not verified and quotes:
            # Keep the first quote unverified rather than returning empty evidence
            logger.warning("quote_verification_failed_fallback", kept=quotes[0][:60])
            return [quotes[0][:150]]
        return [q[:150] for q in verified]

    @staticmethod
    def _fallback_explain(
        inconsistencies: list,
    ) -> tuple[list[ExplanationEntry], str]:
        """Rule-based fallback explanation generator (used when no LLM is available)."""
        entries: list[ExplanationEntry] = []
        for inc in inconsistencies:
            itype = inc.get("type", "OTHER")
            sev = inc.get("severity", "MEDIUM")
            # Log the ReAct steps even in fallback mode for auditability
            observe = (
                f"Statement A: \"{inc.get('statement_a', '')[:100]}\" — "
                f"Statement B: \"{inc.get('statement_b', '')[:100]}\""
            )
            reason = (
                f"Conflict type: {itype.replace('_', ' ').lower()} "
                f"(severity: {sev}). "
                f"{inc.get('explanation', 'Two statements appear to contradict each other.')}"
            )
            detection_method = inc.get("detection_method", "rule_based")
            source_confidence = inc.get("confidence", "MEDIUM")
            logger.info(
                "react_reasoning_chain_fallback",
                inconsistency_id=inc.get("inconsistency_id", "INC?"),
                observe=observe,
                reason=reason,
                detection_method=detection_method,
                source_confidence=source_confidence,
            )
            entry = ExplanationEntry(
                inconsistency_id=inc.get("inconsistency_id", "INC?"),
                plain_english=(
                    f"A {itype.replace('_', ' ').lower()} was detected ({sev} severity). "
                    f"{inc.get('explanation', 'Two statements appear to contradict each other.')}"
                ),
                evidence_quotes=[
                    q for q in [
                        inc.get("statement_a", "")[:150],
                        inc.get("statement_b", "")[:150],
                    ] if q
                ],
                confidence="MEDIUM",
                recommendation="Review the relevant portions of the transcript with the parties involved.",
            )
            # Carry provenance from the consistency agent for report traceability
            entry["detection_method"] = detection_method
            entry["source_confidence"] = source_confidence
            entries.append(entry)
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
        lines += ["", f"**Confidence:** {exp['confidence']}"]
        if exp.get("detection_method"):
            method_label = exp["detection_method"].replace("_", " ").title()
            lines.append(f"**Detection Method:** {method_label}")
        if exp.get("source_confidence"):
            rubric_text = CONFIDENCE_RUBRIC.get(exp["source_confidence"], "")
            lines.append(f"**Detection Confidence:** {exp['source_confidence']} — {rubric_text}")
        lines += [
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
