"""
TRUTHFORGE AI — Fairness / Neutrality Unit Tests
==================================================
Tests the explainability agent's fallback output for neutrality
and verifies that the system prompt's fairness rules are reflected
in rule-based explanations.

Also tests the new inter-agent communication fields (AgentStatus)
and the updated state contract.
"""

from __future__ import annotations
import pytest
from agents.explainability_agent import ExplainabilityAgent, _build_clean_report, PROMPT_VERSION
from agents.responsible_ai_security_agent import ResponsibleAISecurityAgent
from core.state import empty_state, AgentStatus, TruthForgeState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def explainability_agent():
    return ExplainabilityAgent()


@pytest.fixture
def security_agent():
    return ResponsibleAISecurityAgent()


@pytest.fixture
def sample_inconsistencies():
    return [
        {
            "inconsistency_id": "INC001",
            "type": "LOCATION_CONFLICT",
            "statement_a": "Witness stated the accused was at Changi Airport at 9:45pm",
            "statement_b": "Complainant stated the accused was at the scene at 9:45pm",
            "event_a_id": "E001",
            "event_b_id": "E002",
            "severity": "HIGH",
            "explanation": "Two witnesses place the accused in different locations at the same time.",
        }
    ]


# ---------------------------------------------------------------------------
# Tests: fallback explanations are neutral
# ---------------------------------------------------------------------------

class TestFallbackExplanationNeutrality:
    """
    Fallback (no-LLM) explanations must not contain conclusion language.
    """

    FORBIDDEN_PHRASES = [
        "is guilty",
        "is innocent",
        "is lying",
        "is truthful",
        "did it",
        "committed the",
        "is responsible for",
        "verdict",
        "tend to be",           # generalisation
        "tend to lie",
        "less credible",
        "more credible",
    ]

    def test_fallback_no_guilt_language(self, explainability_agent, sample_inconsistencies):
        result = explainability_agent.run(
            inconsistencies=sample_inconsistencies,
            raw_transcript="Sample transcript.",
            llm=None,
        )
        full_text = "\n".join(
            exp.get("plain_english", "") + " " + exp.get("recommendation", "")
            for exp in result["explanations"]
        ) + result.get("final_report", "")

        for phrase in self.FORBIDDEN_PHRASES:
            assert phrase.lower() not in full_text.lower(), (
                f"Forbidden phrase '{phrase}' found in fallback explanation output. "
                "Update _fallback_explain() to remove this language."
            )

    def test_fallback_no_inconsistencies_is_neutral(self, explainability_agent):
        result = explainability_agent.run(
            inconsistencies=[],
            raw_transcript="Short neutral transcript.",
            llm=None,
        )
        assert result["explanations"][0]["inconsistency_id"] == "NONE"
        report = result.get("final_report", "")
        for phrase in self.FORBIDDEN_PHRASES:
            assert phrase.lower() not in report.lower()


# ---------------------------------------------------------------------------
# Tests: final report structure
# ---------------------------------------------------------------------------

class TestFinalReportStructure:
    """Verify _build_clean_report() always includes the disclaimer."""

    DISCLAIMER_FRAGMENT = "does not constitute legal advice"

    def test_report_includes_disclaimer(self, sample_inconsistencies):
        from core.state import ExplanationEntry
        explanations = [
            ExplanationEntry(
                inconsistency_id="INC001",
                plain_english="Two statements conflict on timing.",
                evidence_quotes=["at 9:45pm", "at 10:00pm"],
                confidence="HIGH",
                recommendation="Request clarification.",
            )
        ]
        report = _build_clean_report(explanations, "Overall transcript is internally inconsistent.")
        assert self.DISCLAIMER_FRAGMENT in report

    def test_empty_report_includes_disclaimer(self):
        report = _build_clean_report([], "No inconsistencies found.")
        assert self.DISCLAIMER_FRAGMENT in report

    def test_report_no_conclusion_language(self):
        from core.state import ExplanationEntry
        explanations = [
            ExplanationEntry(
                inconsistency_id="INC001",
                plain_english="The two accounts conflict.",
                evidence_quotes=[],
                confidence="MEDIUM",
                recommendation="Review transcript section 3.",
            )
        ]
        report = _build_clean_report(explanations, "Minor issue detected.")
        forbidden = ["is guilty", "is innocent", "verdict:", "he did it"]
        for phrase in forbidden:
            assert phrase.lower() not in report.lower()


# ---------------------------------------------------------------------------
# Tests: prompt version constant exists
# ---------------------------------------------------------------------------

class TestPromptVersionTracking:
    def test_prompt_version_is_set(self):
        assert PROMPT_VERSION is not None
        assert PROMPT_VERSION.startswith("v"), (
            f"PROMPT_VERSION should start with 'v', got: {PROMPT_VERSION}"
        )


# ---------------------------------------------------------------------------
# Tests: AgentStatus state contract (inter-agent communication v1.1)
# ---------------------------------------------------------------------------

class TestAgentStatusContract:
    """Verify the new state fields are present and properly initialised."""

    def test_empty_state_has_new_fields(self):
        state = empty_state("test transcript")
        assert "agent_statuses" in state
        assert "requires_review" in state
        assert "complexity_level" in state
        assert "run_id" in state
        assert state["agent_statuses"] == {}
        assert state["requires_review"] is False
        assert state["complexity_level"] == "STANDARD"
        assert state["run_id"] is None

    def test_agent_status_typed_dict(self):
        status = AgentStatus(
            source_agent="test_agent",
            status="complete",
            confidence="HIGH",
            next_action="proceed_to_next",
            notes="test notes",
        )
        assert status["source_agent"] == "test_agent"
        assert status["confidence"] == "HIGH"
        assert status["status"] == "complete"

    def test_agent_statuses_accumulate(self):
        """Multiple agents can write to agent_statuses without overwriting."""
        statuses = {}
        statuses["agent_a"] = AgentStatus(
            source_agent="agent_a", status="complete",
            confidence="HIGH", next_action="next", notes=""
        )
        statuses["agent_b"] = AgentStatus(
            source_agent="agent_b", status="complete",
            confidence="MEDIUM", next_action="end", notes=""
        )
        assert len(statuses) == 2
        assert statuses["agent_a"]["confidence"] == "HIGH"
        assert statuses["agent_b"]["confidence"] == "MEDIUM"


# ---------------------------------------------------------------------------
# Tests: output gate catches biased output (integration with filter)
# ---------------------------------------------------------------------------

class TestOutputGateBiasIntegration:
    """Verify the security agent's output gate catches bias from any source."""

    def test_output_gate_catches_race_generalisation(self, security_agent):
        report_with_bias = (
            "## Analysis\n\n"
            "The inconsistency is notable. Chinese witnesses tend to be more reliable "
            "in court proceedings than foreign witnesses. This affects our confidence.\n"
        )
        result = security_agent.filter_output(report_with_bias)
        # Either bias_detected or neutrality_violation should be in violations
        assert not result.is_clean or len(result.violations) > 0 or \
               "REDACTED" in result.filtered_text, (
            "Output gate failed to flag or redact a report with race generalisation."
        )

    def test_output_gate_passes_clean_analysis(self, security_agent):
        clean = (
            "Statement A conflicts with Statement B on the question of the accused's "
            "location at 9:45pm. This requires further investigation by the legal team."
        )
        result = security_agent.filter_output(clean)
        assert result.is_clean
