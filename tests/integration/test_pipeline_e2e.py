"""
Integration tests: End-to-end pipeline tests (no LLM — fallback mode).
Tests the full LangGraph pipeline without requiring API keys.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestPipelineEndToEnd:
    """End-to-end pipeline integration tests using fallback (no LLM)."""

    def test_clean_transcript_pipeline(self, clean_transcript):
        """Clean transcript should pass security and produce a report."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(clean_transcript, llm_config=None)
        assert result is not None
        assert result.get("error_state") is None or "BLOCKED" not in str(result.get("error_state", ""))
        assert result["sanitized_transcript"] != ""
        assert not result["security_input_blocked"]

    def test_injection_transcript_is_blocked(self, injection_transcript):
        """Adversarial transcript must be blocked before reaching processing agents."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(injection_transcript, llm_config=None)
        assert result["security_input_blocked"] is True
        assert len(result["security_input_flags"]) > 0
        # No entities or timeline should be generated
        assert result["entities"] == []
        assert result["timeline"] == []

    def test_pipeline_produces_audit_log(self, clean_transcript):
        """Audit log must have entries from multiple agents."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(clean_transcript, llm_config=None)
        assert len(result["audit_log"]) >= 3

    def test_pipeline_state_has_all_keys(self, clean_transcript):
        """Final state must have all expected TruthForgeState keys."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(clean_transcript, llm_config=None)
        required_keys = [
            "raw_transcript", "sanitized_transcript", "security_input_flags",
            "security_input_blocked", "entities", "structured_facts", "timeline",
            "inconsistencies", "explanations", "security_output_flags",
            "final_report", "audit_log", "error_state",
        ]
        for key in required_keys:
            assert key in result, f"Missing key in final state: {key}"

    def test_final_report_has_content(self, clean_transcript):
        """Final report must be non-empty."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(clean_transcript, llm_config=None)
        if not result["security_input_blocked"]:
            assert result["final_report"].strip() != ""

    def test_final_report_contains_disclaimer(self, clean_transcript):
        """Final report must contain the responsible AI disclaimer."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(clean_transcript, llm_config=None)
        if not result["security_input_blocked"]:
            report_lower = result["final_report"].lower()
            assert "does not constitute" in report_lower or "analytical aid" in report_lower or "human" in report_lower

    def test_raw_transcript_preserved(self, clean_transcript):
        """Raw transcript must be preserved unchanged in state."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(clean_transcript, llm_config=None)
        assert result["raw_transcript"] == clean_transcript

    def test_contradictory_transcript_pipeline_runs(self, contradictory_transcript):
        """Contradictory transcript should pass security and complete pipeline."""
        from agents.orchestration_agent import run_pipeline
        result = run_pipeline(contradictory_transcript, llm_config=None)
        assert not result["security_input_blocked"]
        # Rule-based may or may not detect the inconsistencies without LLM,
        # but the pipeline must complete without error
        assert result.get("error_state") is None or "BLOCKED" not in str(result.get("error_state", ""))


class TestPipelineStreaming:
    """Test the streaming pipeline variant."""

    def test_stream_yields_node_updates(self, clean_transcript):
        from agents.orchestration_agent import stream_pipeline
        updates = list(stream_pipeline(clean_transcript, llm_config=None))
        assert len(updates) > 0
        # Each update is (node_name, state_update)
        for node_name, state_update in updates:
            assert isinstance(node_name, str)
            assert isinstance(state_update, dict)

    def test_injection_blocked_in_stream(self, injection_transcript):
        from agents.orchestration_agent import stream_pipeline
        all_updates = dict()
        for node_name, state_update in stream_pipeline(injection_transcript, llm_config=None):
            all_updates[node_name] = state_update
        # Security input should have blocked it
        security_update = all_updates.get("security_input", {})
        assert security_update.get("security_input_blocked") is True
