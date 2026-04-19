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


class TestExplainabilityReActStructure:
    """Verify the ReAct framework is correctly defined in the agent's prompt and schema."""

    @pytest.fixture
    def agent(self):
        return ExplainabilityAgent()

    def test_system_prompt_contains_all_react_steps(self):
        """System prompt must explicitly define all four ReAct steps."""
        from agents.explainability_agent import _SYSTEM_PROMPT
        for step in ["OBSERVE", "REASON", "EXPLAIN", "RECOMMEND"]:
            assert step in _SYSTEM_PROMPT, f"Missing ReAct step in system prompt: {step}"

    def test_explanation_model_has_observe_and_reason_fields(self):
        """ExplanationModel schema must expose observe and reason as separate fields."""
        from agents.explainability_agent import ExplanationModel
        fields = ExplanationModel.model_fields
        assert "observe" in fields, "ExplanationModel missing 'observe' field"
        assert "reason" in fields, "ExplanationModel missing 'reason' field"

    def test_prompt_version_logged_on_start(self, agent, sample_inconsistencies):
        """PROMPT_VERSION must appear in the first audit log entry."""
        from agents.explainability_agent import PROMPT_VERSION
        result = agent.run(sample_inconsistencies, "Sample transcript.", llm=None)
        assert any(PROMPT_VERSION in entry for entry in result["audit_log"])


class TestExplainabilitySecurityAndFairness:
    """Security and responsible-AI tests for the Explainability Agent."""

    @pytest.fixture
    def agent(self):
        return ExplainabilityAgent()

    def test_evidence_quotes_capped_at_150_chars_in_fallback(self, agent):
        """Fallback evidence quotes must not exceed 150 characters."""
        long_statement = "A" * 300
        inc = [{
            "inconsistency_id": "INC001",
            "type": "LOCATION_CONFLICT",
            "statement_a": long_statement,
            "statement_b": "Short statement.",
            "severity": "HIGH",
            "explanation": "Locations conflict.",
        }]
        result = agent.run(inc, long_statement, llm=None)
        for exp in result["explanations"]:
            for q in exp["evidence_quotes"]:
                assert len(q) <= 150, f"Quote exceeds 150 chars: {q!r}"

    def test_malformed_inconsistency_input_does_not_crash(self, agent):
        """Agent must handle inconsistency dicts with missing fields gracefully."""
        bad_inputs = [
            {"inconsistency_id": "INC001"},                  # all other fields missing
            {},                                               # completely empty
            {"type": "LOCATION_CONFLICT", "severity": "HIGH"},  # no ID
        ]
        result = agent.run(bad_inputs, "Some transcript text.", llm=None)
        assert "explanations" in result
        assert len(result["explanations"]) == len(bad_inputs)

    def test_no_identity_bias_in_fallback_output(self, agent):
        """Fallback explanations must not produce identity-based language."""
        inc = [{
            "inconsistency_id": "INC001",
            "type": "STATEMENT_CONFLICT",
            "statement_a": "The foreign worker said he was at home.",
            "statement_b": "The employer said he was at work.",
            "severity": "MEDIUM",
            "explanation": "Accounts of location differ.",
        }]
        result = agent.run(inc, "Foreign worker transcript.", llm=None)
        report_lower = result["final_report"].lower()
        for phrase in ["as a foreigner", "people like him", "given her background",
                       "clearly lying", "obviously fabricated"]:
            assert phrase not in report_lower, f"Found bias phrase: {phrase!r}"

    def test_react_reasoning_chain_logged_in_fallback(self, agent):
        """ReAct reasoning chain must be logged via logger.info for each
        inconsistency processed in fallback mode."""
        from unittest.mock import patch
        inc = [{
            "inconsistency_id": "INC001",
            "type": "LOCATION_CONFLICT",
            "statement_a": "He was at the airport.",
            "statement_b": "She saw him at the carpark.",
            "severity": "HIGH",
            "explanation": "Location conflict.",
            "detection_method": "rule_based",
            "confidence": "HIGH",
        }]
        with patch("agents.explainability_agent.logger") as mock_logger:
            agent.run(inc, "He was at the airport. She saw him at the carpark.", llm=None)
        logged_events = [str(call) for call in mock_logger.info.call_args_list]
        assert any("react_reasoning_chain_fallback" in evt for evt in logged_events), (
            "Expected react_reasoning_chain_fallback to be logged for each inconsistency"
        )

    def test_bias_scanner_flags_unsafe_phrase_in_llm_output(self):
        """_check_output_bias must detect forbidden phrases in plain_english."""
        from agents.explainability_agent import ExplainabilityAgent
        agent = ExplainabilityAgent()
        entries = [{
            "inconsistency_id": "INC001",
            "plain_english": "The witness is clearly lying about their location.",
            "recommendation": "Review transcript.",
            "confidence": "HIGH",
            "evidence_quotes": [],
        }]
        bias_audits = agent._check_output_bias(entries)
        assert len(bias_audits) >= 1, "Expected bias scanner to flag 'clearly lying'"

    def test_bias_scanner_passes_clean_output(self):
        """_check_output_bias must return empty list for clean explanation text."""
        from agents.explainability_agent import ExplainabilityAgent
        agent = ExplainabilityAgent()
        entries = [{
            "inconsistency_id": "INC001",
            "plain_english": "Statement A places the witness at location X. Statement B places them at location Y.",
            "recommendation": "Request clarification from the witness on their location.",
            "confidence": "HIGH",
            "evidence_quotes": [],
        }]
        bias_audits = agent._check_output_bias(entries)
        assert bias_audits == [], f"Expected no bias flags on clean text, got: {bias_audits}"

    def test_confidence_rubric_is_defined_for_all_levels(self):
        """CONFIDENCE_RUBRIC must define HIGH, MEDIUM, and LOW with non-empty descriptions."""
        from agents.explainability_agent import CONFIDENCE_RUBRIC
        for level in ("HIGH", "MEDIUM", "LOW"):
            assert level in CONFIDENCE_RUBRIC, f"Missing rubric entry for: {level}"
            assert len(CONFIDENCE_RUBRIC[level]) > 10, f"Rubric too short for: {level}"

    def test_detection_method_carried_from_inconsistency(self, agent):
        """detection_method from the consistency agent must appear in the explanation entry."""
        inc = [{
            "inconsistency_id": "INC001",
            "type": "LOCATION_CONFLICT",
            "statement_a": "He was at Changi Airport.",
            "statement_b": "She saw him at the carpark.",
            "severity": "HIGH",
            "explanation": "Location conflict.",
            "detection_method": "rule_based",
            "confidence": "HIGH",
        }]
        result = agent.run(inc, "He was at Changi Airport. She saw him at the carpark.", llm=None)
        entry = result["explanations"][0]
        assert entry.get("detection_method") == "rule_based"
        assert entry.get("source_confidence") == "HIGH"

    def test_report_includes_detection_method_and_confidence_rubric(self, agent):
        """Final report must show Detection Method and Detection Confidence lines."""
        inc = [{
            "inconsistency_id": "INC001",
            "type": "TEMPORAL_ORDER",
            "statement_a": "Left in June 2023.",
            "statement_b": "Last act dated August 2023.",
            "severity": "HIGH",
            "explanation": "Temporal impossibility.",
            "detection_method": "rule_based",
            "confidence": "HIGH",
        }]
        result = agent.run(inc, "Left in June 2023. Last act dated August 2023.", llm=None)
        report = result["final_report"]
        assert "Detection Method" in report
        assert "Detection Confidence" in report

    def test_verify_quotes_filters_hallucinated_content(self):
        """_verify_quotes must drop quotes not present in transcript."""
        from agents.explainability_agent import ExplainabilityAgent
        agent = ExplainabilityAgent()
        transcript = "The defendant was at Changi Airport at 9:45pm."
        quotes = [
            "The defendant was at Changi Airport",    # present ✓
            "This never appeared in the transcript",  # not present ✗
        ]
        verified = agent._verify_quotes(quotes, transcript)
        assert len(verified) == 1
        assert "Changi Airport" in verified[0]
