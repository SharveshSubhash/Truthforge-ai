"""
TRUTHFORGE AI — Consistency Analysis Agent
================================================================
Detects logical inconsistencies in the reconstructed timeline and
structured facts.

Types of inconsistency detected
---------------------------------
• DATE_MISMATCH      — same actor/event referenced with different dates
• LOCATION_CONFLICT  — actor stated to be in two places simultaneously
• ACTOR_CONFLICT     — contradictory attribution of an action
• TEMPORAL_ORDER     — event A described as happening before B, but timeline shows opposite
• STATEMENT_CONFLICT — two verbatim statements directly contradict each other
• OTHER              — any other logical conflict

Output
------
list[Inconsistency] with severity LOW / MEDIUM / HIGH

Standalone usage
----------------
    from agents.consistency_analysis_agent import ConsistencyAnalysisAgent
    from config import get_llm
    agent = ConsistencyAnalysisAgent()
    result = agent.run(timeline, entities, structured_facts, llm=get_llm(...))
"""

from __future__ import annotations
from langchain_core.runnables import RunnableConfig
import json
from typing import Optional

from pydantic import BaseModel, Field

from core.state import Inconsistency
from core.logger import audit, get_logger

logger = get_logger("consistency_analysis_agent")


# ---------------------------------------------------------------------------
# Pydantic schema for LLM structured output
# ---------------------------------------------------------------------------

class InconsistencyModel(BaseModel):
    inconsistency_id: str = Field(description="Unique ID, e.g. 'INC001'")
    type: str = Field(
        description="One of: DATE_MISMATCH, LOCATION_CONFLICT, ACTOR_CONFLICT, "
                    "TEMPORAL_ORDER, STATEMENT_CONFLICT, OTHER"
    )
    statement_a: str = Field(description="First conflicting statement (verbatim from transcript)")
    statement_b: str = Field(description="Second conflicting statement (verbatim from transcript)")
    event_a_id: Optional[str] = Field(None, description="event_id of first event, if applicable")
    event_b_id: Optional[str] = Field(None, description="event_id of second event, if applicable")
    severity: str = Field(description="HIGH (material contradiction), MEDIUM (notable), LOW (minor)")
    explanation: str = Field(description="One sentence explaining the contradiction")


class ConsistencyReportModel(BaseModel):
    inconsistencies: list[InconsistencyModel] = Field(
        description="All detected inconsistencies, empty list if none found"
    )
    overall_consistency: str = Field(
        description="CONSISTENT, MINOR_ISSUES, or SIGNIFICANT_ISSUES"
    )
    analysis_notes: str = Field(
        description="Brief notes on what was checked and any limitations"
    )


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """

You are a legal consistency analyst specialising in Singapore court proceedings. Your role is to detect ALL types of logical inconsistencies, contradictions, and anomalies in legal transcript evidence.

You will be given:
1. The FULL raw transcript text (primary source — always prefer this)
2. A reconstructed timeline of events
3. Key factual statements extracted from the transcript

TYPES OF INCONSISTENCY TO DETECT:

A. TEMPORAL / LOCATION CONFLICTS
   - Same person claimed to be in two different places at the same time
   - Dates or times that directly contradict each other for the same event
   - Events recorded in an impossible chronological order
   - A person blamed for an act that occurred AFTER they had already left (e.g., left a job in June but accused of an act in August)

B. STATEMENT CONFLICTS (Between witnesses or between statements)
   - One witness says X; another witness says Y about the same fact
   - A party's in-court testimony contradicts their earlier police statement
   - A party gives different numbers, descriptions, or sequences at different points

C. EVOLVING / DELAYED TESTIMONY
   - Key information (alibi, named third party, new facts) first appears much later than expected
   - A party changes their account when confronted with evidence
   - A statement is made in court that contradicts a statement made to police
   - A witness cannot recall basic facts they would reasonably be expected to know

D. LOGICAL IMPOSSIBILITIES
   - The accused blames someone who logically could not have done it (wrong time, wrong place, already gone)
   - Actions described that are physically impossible given other established facts
   - Numbers or quantities that do not add up

E. INTERNAL SELF-CONTRADICTIONS
   - A single witness contradicts themselves within their own testimony
   - An account that is inconsistent with documentary evidence cited in the same transcript (receipts, records, CCTV)

INSTRUCTIONS:
1. Read the FULL raw transcript carefully — do not rely solely on the structured extraction.
2. For each inconsistency, quote the EXACT conflicting passages from the transcript (verbatim).
3. Assign severity:
   - HIGH = directly material to the outcome (alibi collapses, key witness contradicted)
   - MEDIUM = notable discrepancy that requires explanation
   - LOW = minor detail difference
4. Be thorough — err on the side of reporting a potential issue rather than missing one.
5. Only report genuine contradictions — vague estimates or differences in recollection precision alone are NOT inconsistencies unless they directly conflict.

CRITICAL RULES:
- Do NOT draw conclusions about guilt, innocence, or credibility of any party.
- Do NOT add information not present in the provided transcript.
- If no inconsistencies are found, return an empty list — do not invent issues.
- Maintain strict legal neutrality throughout.
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class ConsistencyAnalysisAgent:
    """Detects inconsistencies across timeline events and statements."""

    def run(
        self,
        timeline: list,
        entities: list,
        structured_facts: dict,
        llm=None,
        raw_transcript: str = "",
    ) -> dict:
        """
        Analyse for inconsistencies.

        Args:
            timeline: list of TimelineEvent dicts
            entities: list of Entity dicts
            structured_facts: output of TranscriptProcessingAgent
            llm: LangChain chat model
            raw_transcript: full sanitized transcript text (primary source for LLM)

        Returns:
            dict with 'inconsistencies' and audit log entries
        """
        log_start = audit("consistency_analysis_agent", "start",
                          timeline_events=len(timeline),
                          statements=len(structured_facts.get("key_statements", [])))

        if not timeline and not structured_facts.get("key_statements") and not raw_transcript:
            log_end = audit("consistency_analysis_agent", "complete_empty")
            return {"inconsistencies": [], "audit_log": [log_start, log_end]}

        if llm is not None:
            inconsistencies = self._llm_analyse(timeline, structured_facts, llm, raw_transcript)
        else:
            inconsistencies = self._rule_based_analyse(timeline, structured_facts, raw_transcript)

        log_end = audit("consistency_analysis_agent", "complete",
                        inconsistencies_found=len(inconsistencies))
        return {"inconsistencies": inconsistencies, "audit_log": [log_start, log_end]}

    def _llm_analyse(
        self,
        timeline: list,
        structured_facts: dict,
        llm,
        raw_transcript: str = "",
    ) -> list[Inconsistency]:
        """LLM-powered consistency analysis — passes the full raw transcript as primary source."""
        try:
            structured_llm = llm.with_structured_output(ConsistencyReportModel)

            # Build user message: raw transcript first (primary), then structured extraction
            user_parts = []
            if raw_transcript:
                user_parts.append(
                    "=== FULL TRANSCRIPT (primary source) ===\n" + raw_transcript
                )
            structured_data = {
                "timeline": timeline,
                "key_statements": structured_facts.get("key_statements", []),
                "events": structured_facts.get("events", []),
            }
            user_parts.append(
                "\n=== STRUCTURED EXTRACTION (secondary reference) ===\n"
                + json.dumps(structured_data, indent=2, default=str)
            )
            user_message = (
                "Please analyse all of the following for inconsistencies. "
                "Prioritise reading the FULL TRANSCRIPT — the structured extraction "
                "is a supplement only and may be incomplete.\n\n"
                + "\n".join(user_parts)
            )

            result: ConsistencyReportModel = structured_llm.invoke([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ])
            return [
                Inconsistency(
                    inconsistency_id=inc.inconsistency_id,
                    type=inc.type,
                    statement_a=inc.statement_a,
                    statement_b=inc.statement_b,
                    event_a_id=inc.event_a_id,
                    event_b_id=inc.event_b_id,
                    severity=inc.severity,
                    explanation=inc.explanation,
                )
                for inc in result.inconsistencies
            ]
        except Exception as exc:
            logger.error("llm_consistency_failed", error=str(exc))
            return self._rule_based_analyse(timeline, structured_facts, raw_transcript)

    @staticmethod
    def _rule_based_analyse(
        timeline: list,
        structured_facts: dict,
        raw_transcript: str = "",
    ) -> list[Inconsistency]:
        """
        Enhanced rule-based fallback analysis.
        Detects five categories of inconsistency without an LLM:
          1. Location conflict — same timestamp, different locations
          2. Statement conflict — key_statements that directly contradict each other
          3. Temporal impossibility — person blamed for act after they left
          4. Evolving testimony — key name/alibi not mentioned until late in transcript
          5. Same-event time discrepancy — same event assigned different times
        """
        inconsistencies: list[Inconsistency] = []
        idx = 0

        def _inc(type_, a, b, ea, eb, severity, explanation):
            nonlocal idx
            idx += 1
            return Inconsistency(
                inconsistency_id=f"INC{str(idx).zfill(3)}",
                type=type_,
                statement_a=a,
                statement_b=b,
                event_a_id=ea,
                event_b_id=eb,
                severity=severity,
                explanation=explanation,
            )

        # ── 1. Location conflict at same timestamp ──────────────────────────
        time_groups: dict[str, list[dict]] = {}
        for ev in timeline:
            nt = ev.get("normalized_time") or "unknown"
            time_groups.setdefault(nt, []).append(ev)

        for nt, evs in time_groups.items():
            if nt == "unknown" or len(evs) < 2:
                continue
            locs = {ev.get("location") for ev in evs if ev.get("location")}
            if len(locs) > 1:
                inconsistencies.append(_inc(
                    "LOCATION_CONFLICT",
                    evs[0].get("source_excerpt", evs[0].get("description", "")),
                    evs[1].get("source_excerpt", evs[1].get("description", "")),
                    evs[0].get("event_id"), evs[1].get("event_id"),
                    "HIGH",
                    f"At {nt}, events reference conflicting locations: "
                    + ", ".join(f"'{l}'" for l in locs),
                ))

        # ── 2. Statement conflict — scan key_statements for time contradictions ──
        import re
        statements = structured_facts.get("key_statements", [])
        _TIME_RE = re.compile(
            r'\b(\d{1,2})[:.h](\d{2})\s*(am|pm)?\b|\b(\d{1,2})\s*(am|pm)\b',
            re.IGNORECASE,
        )

        _UNIT_RE = re.compile(r'^\s*(?:grams?|mg|ml|kg|g\b|mcg|oz)', re.IGNORECASE)

        def _extract_times(text: str) -> list[str]:
            results = []
            for m in _TIME_RE.finditer(text):
                # Skip drug / weight measurements like "14.76 grams" or "28.63g"
                after = text[m.end():m.end() + 10]
                if _UNIT_RE.match(after):
                    continue
                results.append(m.group(0).lower().strip())
            return results

        def _time_to_minutes(t: str) -> int | None:
            """Convert a time string like '10:45pm' or '2am' to minutes since midnight."""
            try:
                t = t.lower().strip()
                is_pm = t.endswith("pm")
                is_am = t.endswith("am")
                t_clean = t.replace("am", "").replace("pm", "").strip()
                if ":" in t_clean or "." in t_clean:
                    sep = ":" if ":" in t_clean else "."
                    parts = t_clean.split(sep)
                    h, m = int(parts[0]), int(parts[1])
                else:
                    h, m = int(t_clean), 0
                if is_pm and h != 12:
                    h += 12
                if is_am and h == 12:
                    h = 0
                if h > 23 or m > 59:   # invalid parsed value (e.g. drug weight)
                    return None
                return h * 60 + m
            except Exception:
                return None

        # Compare each pair of statements that share an actor or event keyword
        for i, s1 in enumerate(statements):
            for j, s2 in enumerate(statements):
                if j <= i:
                    continue
                t1 = _extract_times(s1)
                t2 = _extract_times(s2)
                if not t1 or not t2:
                    continue
                # Only flag if times differ by at least 15 minutes — small gaps
                # (< 15 min) represent sequential events, not contradictions.
                m1 = _time_to_minutes(t1[0])
                m2 = _time_to_minutes(t2[0])
                if m1 is not None and m2 is not None:
                    diff = abs(m1 - m2)
                    # handle midnight wrap-around (e.g. 11:50pm vs 0:10am = 20 min)
                    diff = min(diff, 1440 - diff)
                    if diff < 15:
                        continue
                # If both statements reference the same time-sensitive phrase but
                # list different times, flag as potential DATE_MISMATCH
                shared_words = (
                    set(re.findall(r'\b[A-Z][a-z]+\b', s1))
                    & set(re.findall(r'\b[A-Z][a-z]+\b', s2))
                )
                if shared_words and t1 != t2:
                    inconsistencies.append(_inc(
                        "DATE_MISMATCH",
                        s1[:300], s2[:300],
                        None, None,
                        "MEDIUM",
                        f"Two statements share context ({', '.join(list(shared_words)[:3])}) "
                        f"but reference different times: {t1[0]} vs {t2[0]}.",
                    ))

        # ── 3. Temporal impossibility — person blamed for act after departure ──
        if raw_transcript:
            _MONTH_MAP = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }
            _MONTH_RE = re.compile(
                r'(january|february|march|april|may|june|july|august|'
                r'september|october|november|december)\s+(\d{4})',
                re.IGNORECASE,
            )
            # FIX: use finditer + .group(0) — findall() with a capturing group
            # returns ONLY the captured word, not the full sentence match.
            departure_re = re.compile(
                r'[^.!?\n]*\b(?:left|resigned|departed|terminated|ceased)\b[^.!?\n]*',
                re.IGNORECASE,
            )
            action_re = re.compile(
                r'[^.!?\n]*\b(?:last|dated|after|until|before|since)\b[^.!?\n]*',
                re.IGNORECASE,
            )
            # Full sentence text is now correctly captured via group(0)
            departure_sentences = [m.group(0) for m in departure_re.finditer(raw_transcript)]
            action_sentences    = [m.group(0) for m in action_re.finditer(raw_transcript)]

            dep_dates: list[tuple] = []
            for sent in departure_sentences:
                for m in _MONTH_RE.finditer(sent):
                    dep_dates.append((
                        _MONTH_MAP[m.group(1).lower()],
                        int(m.group(2)),
                        sent.strip()[:400],
                    ))

            act_dates: list[tuple] = []
            for sent in action_sentences:
                for m in _MONTH_RE.finditer(sent):
                    act_dates.append((
                        _MONTH_MAP[m.group(1).lower()],
                        int(m.group(2)),
                        sent.strip()[:400],
                    ))

            flagged_dep: set = set()
            for dep_month, dep_year, dep_sent in dep_dates:
                if dep_sent in flagged_dep:
                    continue
                for act_month, act_year, act_sent in act_dates:
                    # Skip if same sentence — a single sentence can hold both dates
                    # (e.g. "X left in June / last voucher in August") — still flag it
                    later = (act_year > dep_year) or (
                        act_year == dep_year and act_month > dep_month
                    )
                    if later and dep_sent != act_sent:
                        inconsistencies.append(_inc(
                            "TEMPORAL_ORDER",
                            dep_sent, act_sent,
                            None, None,
                            "HIGH",
                            f"A departure/exit is recorded in "
                            f"{_MONTH_MAP_INV.get(dep_month, dep_month)}/{dep_year}, "
                            f"but a related act is dated "
                            f"{_MONTH_MAP_INV.get(act_month, act_month)}/{act_year} "
                            "— after the departure.",
                        ))
                        flagged_dep.add(dep_sent)
                        break
                # Also flag when BOTH dates are in the same sentence
                # (writer explicitly noted the contradiction in one line)
                for m2 in _MONTH_RE.finditer(dep_sent):
                    m2_month = _MONTH_MAP[m2.group(1).lower()]
                    m2_year  = int(m2.group(2))
                    if (m2_year > dep_year) or (m2_year == dep_year and m2_month > dep_month):
                        inconsistencies.append(_inc(
                            "TEMPORAL_ORDER",
                            dep_sent, dep_sent,
                            None, None,
                            "HIGH",
                            f"A single passage records a departure in "
                            f"{dep_month}/{dep_year} alongside an act in "
                            f"{m2_month}/{m2_year} — a temporal impossibility.",
                        ))
                        flagged_dep.add(dep_sent)
                        break

        # ── 4. Evolving testimony — name appears only in later part of transcript ──
        if raw_transcript:
            lines = raw_transcript.splitlines()
            midpoint = len(lines) // 2
            first_half  = "\n".join(lines[:midpoint])
            second_half = "\n".join(lines[midpoint:])

            # Match names like "Brandon Seet" or "Ahmad bin Salleh"
            _NAME_RE = re.compile(
                r'\b([A-Z][a-z]{1,20}(?:\s+(?:bin|bte|s/o|d/o|al))?'
                r'\s+[A-Z][a-z]{1,20})\b'
            )
            # Titles / ranks that appear as part of formal witness introductions
            _RANK_PREFIX = re.compile(
                r'^(?:Corporal|Sergeant|Sgt|Staff\s+Sergeant|SSgt|Inspector|'
                r'Insp|Senior\s+Staff\s+Sergeant|Staff|Officer|Detective|'
                r'Constable|Captain|Lieutenant|Major|Colonel|Dr|Doctor|'
                r'Professor|Prof|Justice|Judge|Magistrate)\b',
                re.IGNORECASE,
            )
            first_names  = set(_NAME_RE.findall(first_half))
            second_names = set(_NAME_RE.findall(second_half))
            # Exclude names that start with a formal rank/title — these are
            # legitimate witnesses introduced in the second half of the transcript,
            # not suspicious late-emerging names.
            late_names   = {
                n for n in (second_names - first_names)
                if not _RANK_PREFIX.match(n)
            }

            # Broader blame/introduction context — includes verb forms
            blame_context = re.compile(
                r'\b(?:blam\w*|responsible|did it|ask\w*|told|tell\w*|said|'
                r'claim\w*|introduc\w*|reveal\w*|discover\w*|'
                r'approach\w*|approv\w*|named|colleague|friend|'
                r'gave\s+me|gave\s+him|deceiv\w*|manipulat\w*)\b',
                re.IGNORECASE,
            )
            for name in late_names:
                name_contexts = [
                    m.group(0).strip()
                    for m in re.finditer(
                        rf'[^.!?\n]*\b{re.escape(name)}\b[^.!?\n]*',
                        second_half,
                    )
                ]
                for ctx in name_contexts:
                    if blame_context.search(ctx):
                        inconsistencies.append(_inc(
                            "STATEMENT_CONFLICT",
                            f"'{name}' does not appear anywhere in the first half of the transcript.",
                            ctx[:400],
                            None, None,
                            "MEDIUM",
                            f"The name '{name}' first appears only in the latter portion "
                            "of the transcript in a context suggesting blame, attribution, "
                            "or new introduction — possible evolving testimony.",
                        ))
                        break  # one flag per new name

        return inconsistencies


# Month number → name mapping (inverse, for human-readable explanations)
_MONTH_MAP_INV = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------

_agent_instance = ConsistencyAnalysisAgent()


def consistency_analysis_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
    """LangGraph node: consistency analysis."""
    if state.get("security_input_blocked"):
        return {"audit_log": [audit("consistency_analysis_agent", "skipped_blocked_input")]}

    llm = None
    if config:
        try:
            from config import get_llm_from_config
            llm = get_llm_from_config(config)
        except Exception as e:
            logger.warning("llm_init_failed", error=str(e))

    # Check if this is a second-pass (uncertain review) invocation
    is_second_pass = (config or {}).get("configurable", {}).get("second_pass", False)
    if is_second_pass:
        audit("consistency_analysis_agent", "second_pass_invoked")

    result = _agent_instance.run(
        timeline=state.get("timeline", []),
        entities=state.get("entities", []),
        structured_facts=state.get("structured_facts", {}),
        llm=llm,
        raw_transcript=state.get("sanitized_transcript", state.get("raw_transcript", "")),
    )

    n_inc = len(result["inconsistencies"])
    n_high = sum(1 for i in result["inconsistencies"] if i.get("severity") == "HIGH")
    # Signal requires_review if findings are ambiguous and we have an LLM
    requires_review = (llm is None and n_inc > 0 and not is_second_pass)

    from core.state import AgentStatus
    status_entry = AgentStatus(
        source_agent="consistency_analysis",
        status="second_pass" if is_second_pass else "complete",
        confidence="HIGH" if llm is not None else "MEDIUM",
        next_action="proceed_to_explainability",
        notes=f"{n_inc} inconsistencies ({n_high} HIGH)",
    )

    return {
        "inconsistencies": result["inconsistencies"],
        "requires_review": requires_review,
        "audit_log": result["audit_log"],
        "agent_statuses": {
            **state.get("agent_statuses", {}),
            "consistency_analysis": status_entry,
        },
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, json
    sample_timeline = [
        {"event_id": "E001", "description": "Defendant at Changi Airport",
         "timestamp": "9:45pm", "normalized_time": "2024-01-15T21:45:00",
         "actors": ["John Tan"], "location": "Changi Airport",
         "source_excerpt": "witness stated he was at Changi Airport at 9:45pm"},
        {"event_id": "E002", "description": "Plaintiff saw defendant at scene",
         "timestamp": "10pm", "normalized_time": "2024-01-15T22:00:00",
         "actors": ["plaintiff", "John Tan"], "location": "crime scene",
         "source_excerpt": "she saw him at the scene at 10pm"},
    ]
    sample_facts = {
        "key_statements": [
            "The defendant was at Changi Airport at 9:45pm.",
            "The plaintiff saw the defendant at the scene at 10pm.",
        ],
        "events": sample_timeline,
    }
    agent = ConsistencyAnalysisAgent()
    result = agent.run(sample_timeline, [], sample_facts)
    print(json.dumps(result, indent=2, default=str))
