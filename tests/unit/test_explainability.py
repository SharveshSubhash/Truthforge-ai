"""
Unit tests for the Explainability Agent.
Tests explanation generation in fallback mode (no LLM needed).
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.explainability_agent import ExplainabilityAgent, _build_clean_report


class TestExplainabilityAgent:

    @pytest.fixture
    def agent(self):
        return ExplainabilityAgent()

    def test_empty_inconsistencies_returns_no_issues_message(self, agent):
        result = agent.run([], "Some transcript text.", llm=None)
        assert "explanations" in result
        assert len(result["explanations"]) == 1
        assert result["explanations"][0]["inconsistency_id"] == "NONE"

    def test_run_returns_expected_keys(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        assert "explanations" in result
        assert "final_report" in result
        assert "audit_log" in result

    def test_explanation_count_matches_inconsistencies(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        assert len(result["explanations"]) == len(sample_inconsistencies)

    def test_explanation_has_required_fields(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        for exp in result["explanations"]:
            assert "inconsistency_id" in exp
            assert "plain_english" in exp
            assert "evidence_quotes" in exp
            assert "confidence" in exp
            assert "recommendation" in exp

    def test_plain_english_is_nonempty(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        for exp in result["explanations"]:
            assert exp["plain_english"].strip() != ""

    def test_final_report_is_markdown(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        report = result["final_report"]
        assert "# TRUTHFORGE" in report

    def test_final_report_contains_disclaimer(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        report = result["final_report"]
        assert "does not constitute legal advice" in report or "analytical aid" in report

    def test_no_guilt_language_in_fallback(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        report = result["final_report"].lower()
        # Fallback explanations must not include legal conclusions
        for phrase in ["is guilty", "is innocent", "I conclude", "verdict"]:
            assert phrase not in report, f"Found forbidden phrase: {phrase!r}"

    def test_audit_log_has_entries(self, agent, sample_inconsistencies):
        result = agent.run(sample_inconsistencies, "Some transcript.", llm=None)
        assert len(result["audit_log"]) >= 2


class TestBuildCleanReport:
    """Test the report builder utility."""

    def test_empty_explanations_returns_report(self):
        report = _build_clean_report([], "No issues found.")
        assert "TRUTHFORGE" in report
        assert "No issues found." in report

    def test_report_contains_inconsistency_ids(self):
        explanations = [
            {
                "inconsistency_id": "INC001",
                "plain_english": "A conflict was detected.",
                "evidence_quotes": ["Quote one"],
                "confidence": "HIGH",
                "recommendation": "Review transcript.",
            }
        ]
        report = _build_clean_report(explanations, "One issue found.")
        assert "INC001" in report
        assert "A conflict was detected." in report
