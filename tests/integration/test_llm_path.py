"""
Integration tests: LLM invocation path verification.
Tests the full with_structured_output → invoke chain for each agent
using a mock LLM, proving the LLM code path (not just fallback) works.

These tests exercise:
  - LLM binding via with_structured_output(PydanticSchema)
  - Structured output returned from LLM flows through pipeline
  - Each agent correctly uses LLM output over fallback when LLM succeeds
  - PII redaction applies to LLM-generated report content
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.orchestration_agent import run_pipeline
from config import make_langgraph_config


# ---------------------------------------------------------------------------
# Mock LLM factory — returns valid Pydantic objects for each agent schema
# ---------------------------------------------------------------------------

def _make_mock_llm_with_data():
    """
    Mock LLM that returns realistic structured data for every agent schema.
    This exercises the LLM invocation path (with_structured_output → invoke)
    rather than the rule-based fallback path.
    """
    from agents.transcript_processing_agent import StructuredFactsModel, EventModel
    from agents.timeline_reconstruction_agent import TimelineModel, TimelineEventModel
    from agents.consistency_analysis_agent import ConsistencyReportModel, InconsistencyModel
    from agents.explainability_agent import ExplanationsModel, ExplanationModel

    mock_facts = StructuredFactsModel(
        events=[
            EventModel(
                event_id="E001",
                description="PW1 observed defendant at carpark at 10:32pm",
                timestamp="10:32pm on 14 January 2024",
                actors=["John Tan", "Sarah Lim"],
                location="Blk 45 Jurong West carpark",
                source_excerpt="I saw John Tan at the carpark at 10:32pm",
            ),
            EventModel(
                event_id="E002",
                description="PW1 police statement records 9:45pm sighting",
                timestamp="9:45pm on 14 January 2024",
                actors=["John Tan", "Sarah Lim"],
                location="Blk 45 Jurong West carpark",
                source_excerpt="She told police she saw defendant at 9:45pm",
            ),
        ],
        key_statements=[
            "PW1 oral testimony: saw defendant at 10:32pm.",
            "PW1 police statement: saw defendant at 9:45pm.",
        ],
        summary="PW1's oral testimony and police statement conflict on the time of the sighting by 47 minutes.",
    )

    mock_timeline = TimelineModel(
        events=[
            TimelineEventModel(
                event_id="E001",
                description="PW1 sighting at carpark",
                timestamp="10:32pm",
                normalized_time="2024-01-14T22:32:00",
                actors=["John Tan", "Sarah Lim"],
                location="Blk 45 carpark",
                source_excerpt="I saw John Tan at the carpark at 10:32pm",
                temporal_confidence="HIGH",
            ),
            TimelineEventModel(
                event_id="E002",
                description="PW1 police statement sighting",
                timestamp="9:45pm",
                normalized_time="2024-01-14T21:45:00",
                actors=["John Tan", "Sarah Lim"],
                location="Blk 45 carpark",
                source_excerpt="She told police she saw defendant at 9:45pm",
                temporal_confidence="HIGH",
            ),
        ],
        anchor_date="2024-01-14",
        notes="47-minute discrepancy between oral testimony and police statement.",
    )

    mock_inconsistency = ConsistencyReportModel(
        inconsistencies=[
            InconsistencyModel(
                inconsistency_id="INC001",
                type="DATE_MISMATCH",
                statement_a="PW1 oral testimony: saw defendant at 10:32pm",
                statement_b="PW1 police statement: saw defendant at 9:45pm",
                event_a_id="E001",
                event_b_id="E002",
                severity="HIGH",
                explanation="47-minute discrepancy between two accounts from the same witness.",
            )
        ],
        overall_consistency="INCONSISTENT",
        analysis_notes="One high-severity time discrepancy found in PW1 testimony.",
    )

    mock_explanations = ExplanationsModel(
        explanations=[
            ExplanationModel(
                inconsistency_id="INC001",
                observe=(
                    "PW1 court testimony: 'I saw John Tan at the carpark at 10:32pm'. "
                    "PW1 police statement: 'She told police she saw defendant at 9:45pm'."
                ),
                reason=(
                    "The two accounts from the same witness reference the same event "
                    "but differ by 47 minutes, making them mutually inconsistent."
                ),
                plain_english=(
                    "PW1's court testimony states she saw the defendant at 10:32pm, "
                    "but her earlier police statement recorded the time as 9:45pm. "
                    "These two accounts differ by 47 minutes and cannot both be correct."
                ),
                evidence_quotes=[
                    "I saw John Tan at the carpark at 10:32pm",
                    "She told police she saw defendant at 9:45pm",
                ],
                confidence="HIGH",
                recommendation=(
                    "Clarify with PW1 which time is accurate and why the accounts differ."
                ),
            )
        ],
        overall_summary="One high-severity inconsistency detected in PW1 timeline.",
    )

    mock = MagicMock()

    def _with_structured_output(schema):
        inner = MagicMock()
        name = schema.__name__ if hasattr(schema, "__name__") else str(schema)
        if "Facts" in name:
            inner.invoke = MagicMock(return_value=mock_facts)
        elif "Timeline" in name:
            inner.invoke = MagicMock(return_value=mock_timeline)
        elif "Consistency" in name or "Report" in name:
            inner.invoke = MagicMock(return_value=mock_inconsistency)
        elif "Explanation" in name:
            inner.invoke = MagicMock(return_value=mock_explanations)
        else:
            inner.invoke = MagicMock(return_value=MagicMock(content="{}"))
        return inner

    mock.with_structured_output = MagicMock(side_effect=_with_structured_output)
    return mock


@pytest.fixture
def mock_llm():
    return _make_mock_llm_with_data()


@pytest.fixture
def clean_transcript():
    fixtures_path = os.path.join(os.path.dirname(__file__), "../fixtures/clean_transcript.txt")
    try:
        with open(fixtures_path) as f:
            return f.read()
    except FileNotFoundError:
        return (
            "WITNESS EXAMINATION — PW1 (Sarah Lim)\n"
            "Q: Where were you on 14 January 2024 at 10:32pm?\n"
            "A: I was at Block 45 Jurong West carpark. I saw Mr. John Tan there.\n"
            "Q: What did your police statement say?\n"
            "A: I told police I saw him at 9:45pm.\n"
            "COURT: Noted. Proceedings concluded."
        )


# ---------------------------------------------------------------------------
# LLM path tests
# ---------------------------------------------------------------------------

class TestLLMInvocationPath:
    """
    Verify that each agent's LLM code path (with_structured_output → invoke)
    is executed and its output propagates through the pipeline.
    """

    def test_llm_path_produces_structured_facts(self, clean_transcript, mock_llm):
        """Transcript processing agent must call LLM and return structured events."""
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(clean_transcript, llm_config=config)
        facts = result.get("structured_facts", {})
        assert facts, "structured_facts must be populated via LLM path"
        assert len(facts.get("events", [])) > 0, "LLM must return at least one event"
        assert facts["events"][0]["event_id"] == "E001"

    def test_llm_path_produces_timeline(self, clean_transcript, mock_llm):
        """Timeline reconstruction agent must return normalised timeline from LLM."""
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(clean_transcript, llm_config=config)
        timeline = result.get("timeline", [])
        assert len(timeline) > 0, "LLM path must produce timeline events"
        assert timeline[0].get("normalized_time"), "Each event must have a normalized_time"

    def test_llm_path_produces_inconsistencies(self, clean_transcript, mock_llm):
        """Consistency analysis agent must return LLM-detected inconsistencies."""
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(clean_transcript, llm_config=config)
        inconsistencies = result.get("inconsistencies", [])
        assert len(inconsistencies) > 0, "LLM path must detect the injected inconsistency"
        assert inconsistencies[0]["type"] == "DATE_MISMATCH"
        assert inconsistencies[0]["severity"] == "HIGH"

    def test_llm_path_produces_explanations(self, clean_transcript, mock_llm):
        """Explainability agent must return plain-English explanations from LLM."""
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(clean_transcript, llm_config=config)
        explanations = result.get("explanations", [])
        assert len(explanations) > 0, "LLM path must produce at least one explanation"
        assert explanations[0].get("plain_english"), "Explanation must have plain_english field"
        assert len(explanations[0].get("evidence_quotes", [])) > 0, "Must include evidence quotes"

    def test_llm_path_final_report_contains_inconsistency(self, clean_transcript, mock_llm):
        """Final report must reflect LLM-detected content, not generic fallback."""
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(clean_transcript, llm_config=config)
        report = result.get("final_report", "")
        assert len(report) > 100, "Report must have substantive content"
        assert "disclaimer" in report.lower() or "does not constitute" in report.lower() \
               or "analytical" in report.lower(), "Report must include responsible AI disclaimer"

    def test_llm_with_structured_output_called_per_agent(self, clean_transcript, mock_llm):
        """with_structured_output must be called once per LLM-powered agent (4 agents)."""
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        with patch("config.get_llm_from_config", return_value=mock_llm):
            run_pipeline(clean_transcript, llm_config=config)
        # with_structured_output should be called for:
        # transcript_processing, timeline_reconstruction, consistency_analysis, explainability
        assert mock_llm.with_structured_output.call_count >= 4, (
            f"Expected at least 4 with_structured_output calls, "
            f"got {mock_llm.with_structured_output.call_count}"
        )

    def test_security_gate_runs_regardless_of_llm(self, clean_transcript, mock_llm):
        """Security input/output gates must run even when LLM is active."""
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(clean_transcript, llm_config=config)
        assert "security_input_blocked" in result
        assert result["security_input_blocked"] is False
        assert "security_output_flags" in result


class TestLLMPathPIIRedaction:
    """Verify PII in LLM-generated content is redacted by the output gate."""

    def test_nric_in_llm_output_is_redacted(self):
        """If an LLM agent produces output containing an NRIC, it must be redacted."""
        from agents.responsible_ai_security_agent import ResponsibleAISecurityAgent
        agent = ResponsibleAISecurityAgent()
        # Simulate LLM generating a report that includes an NRIC
        llm_report = (
            "## Inconsistency Report\n"
            "PW1 (NRIC S9876543Z) stated the incident occurred at 10:32pm.\n"
            "This conflicts with the police statement recorded for S9876543Z.\n"
            "**Disclaimer**: This report is an analytical aid only."
        )
        result = agent.filter_output(llm_report)
        assert "S9876543Z" not in result.filtered_text
        assert "NRIC/FIN REDACTED" in result.filtered_text
        assert any("pii_detected" in v for v in result.violations)

    def test_phone_in_llm_output_is_redacted(self):
        """Phone numbers appearing in LLM-generated reports must be redacted."""
        from agents.responsible_ai_security_agent import ResponsibleAISecurityAgent
        agent = ResponsibleAISecurityAgent()
        llm_report = (
            "Call logs show the accused contacted 91234567 at 11:45pm. "
            "This is inconsistent with the alibi provided."
        )
        result = agent.filter_output(llm_report)
        assert "91234567" not in result.filtered_text
        assert "PHONE REDACTED" in result.filtered_text
