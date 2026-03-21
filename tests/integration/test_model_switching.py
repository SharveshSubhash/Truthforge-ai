"""
Integration tests — Model Switching
Verifies that the LangGraph pipeline produces valid, consistent output
when the model provider configuration is changed.

All tests run in fallback mode (no LLM API keys required) to ensure
CI/CD compatibility. The key assertion is that the *pipeline structure*
and *output schema* are provider-agnostic — not that specific LLM
providers produce identical content (which is non-deterministic).
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage

from agents.orchestration_agent import run_pipeline
from config import make_langgraph_config, ALL_MODELS, get_llm_from_config
from core.state import TruthForgeState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_llm():
    """
    Build a mock LLM that returns structured output conforming to each
    agent's Pydantic schema. Used to test model-switching without API calls.
    """
    mock = MagicMock()

    # Transcript processing mock
    from agents.transcript_processing_agent import StructuredFactsModel, EventModel
    mock_facts = StructuredFactsModel(
        events=[
            EventModel(
                event_id="E001",
                description="Mock event from model switch test",
                timestamp="10:00am",
                actors=["PW1"],
                location="Mock location",
                source_excerpt="Mock excerpt",
            )
        ],
        key_statements=["PW1 stated the event occurred at 10:00am"],
    )

    # Timeline mock
    from agents.timeline_reconstruction_agent import TimelineModel, TimelineEventModel
    mock_timeline = TimelineModel(
        events=[
            TimelineEventModel(
                event_id="E001",
                description="Mock event",
                timestamp="10:00am",
                normalized_time="2024-01-15T10:00:00",
                actors=["PW1"],
                location="Mock location",
                source_excerpt="Mock excerpt",
                temporal_confidence="HIGH",
            )
        ],
        anchor_date="2024-01-15",
        notes="Mock temporal notes",
    )

    # Consistency mock
    from agents.consistency_analysis_agent import ConsistencyReportModel
    mock_consistency = ConsistencyReportModel(
        inconsistencies=[],
        overall_consistency="CONSISTENT",
        analysis_notes="No inconsistencies found in mock data",
    )

    # Explainability mock
    from agents.explainability_agent import ExplanationsModel, ExplanationModel
    mock_explanations = ExplanationsModel(
        explanations=[
            ExplanationModel(
                inconsistency_id="NO_ISSUES",
                plain_english="No inconsistencies were detected in this transcript.",
                evidence_quotes=[],
                confidence="HIGH",
                recommendation="No follow-up action required.",
            )
        ],
        overall_summary="The transcript is internally consistent.",
    )

    # Wire up with_structured_output to return appropriate schema
    def _with_structured_output(schema):
        inner = MagicMock()
        schema_name = schema.__name__ if hasattr(schema, "__name__") else str(schema)
        if "Facts" in schema_name:
            inner.invoke = MagicMock(return_value=mock_facts)
        elif "Timeline" in schema_name:
            inner.invoke = MagicMock(return_value=mock_timeline)
        elif "Consistency" in schema_name or "Report" in schema_name:
            inner.invoke = MagicMock(return_value=mock_consistency)
        elif "Explanation" in schema_name:
            inner.invoke = MagicMock(return_value=mock_explanations)
        else:
            inner.invoke = MagicMock(return_value=AIMessage(content="{}"))
        return inner

    mock.with_structured_output = _with_structured_output
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_transcript():
    try:
        with open("tests/fixtures/clean_transcript.txt") as f:
            return f.read()
    except FileNotFoundError:
        return (
            "WITNESS EXAMINATION — PW1\n"
            "Q: Where were you on 14 January 2024 at 10:32pm?\n"
            "A: I was at Block 45 Jurong West Street 42.\n"
            "COURT: Proceedings concluded at 11:00pm on 14 January 2024."
        )


@pytest.fixture
def mock_llm():
    return _make_mock_llm()


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestModelConfigs:
    """Verify that make_langgraph_config produces valid configs for all models."""

    def test_cloud_model_config(self):
        config = make_langgraph_config("Claude Sonnet 4.6 (Anthropic)")
        assert config["configurable"]["model"] == "claude-sonnet-4-6"
        assert config["configurable"]["model_provider"] == "anthropic"

    def test_openai_model_config(self):
        config = make_langgraph_config("GPT-4o (OpenAI)")
        assert config["configurable"]["model"] == "gpt-4o"
        assert config["configurable"]["model_provider"] == "openai"

    def test_google_model_config(self):
        config = make_langgraph_config("Gemini 2.0 Flash (Google)")
        assert config["configurable"]["model"] == "gemini-2.0-flash"
        assert config["configurable"]["model_provider"] == "google_genai"

    def test_ollama_model_config(self):
        config = make_langgraph_config("Llama 3.1 8B (Ollama)")
        assert config["configurable"]["model"] == "llama3.1:8b"
        assert config["configurable"]["model_provider"] == "ollama"

    def test_all_cloud_models_have_valid_configs(self):
        """All models in ALL_MODELS should produce non-None configs."""
        for label in ALL_MODELS:
            config = make_langgraph_config(label)
            assert config is not None, f"Config is None for model: {label}"
            assert "configurable" in config

    def test_unknown_model_defaults_gracefully(self):
        """Unknown model label falls back to a safe config."""
        config = make_langgraph_config("Nonexistent Model (XYZ)")
        # Should still return a dict with configurable key
        assert isinstance(config, dict)


# ---------------------------------------------------------------------------
# Pipeline output schema consistency across providers
# ---------------------------------------------------------------------------

class TestPipelineSchemaConsistency:
    """
    Verify that switching the model provider does not change the output schema.
    Uses mocked LLMs so no API keys are required.
    """

    @pytest.mark.parametrize("model_label", [
        "Claude Sonnet 4.6 (Anthropic)",
        "GPT-4o (OpenAI)",
        "Gemini 2.0 Flash (Google)",
        "Llama 3.1 8B (Ollama)",
    ])
    def test_output_schema_consistent_across_providers(
        self, clean_transcript, mock_llm, model_label
    ):
        """
        All providers should produce a TruthForgeState with the same
        set of required keys populated.
        """
        config = make_langgraph_config(model_label)

        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(
                transcript=clean_transcript,
                llm_config=config,
            )

        # All required keys must be present
        required_keys = [
            "raw_transcript",
            "sanitized_transcript",
            "entities",
            "timeline",
            "inconsistencies",
            "explanations",
            "final_report",
            "audit_log",
        ]
        for key in required_keys:
            assert key in result, (
                f"Key '{key}' missing from result for model '{model_label}'"
            )

    @pytest.mark.parametrize("model_label", [
        "Claude Sonnet 4.6 (Anthropic)",
        "GPT-4o (OpenAI)",
    ])
    def test_audit_log_populated_for_all_providers(
        self, clean_transcript, mock_llm, model_label
    ):
        """Audit log must have entries regardless of provider."""
        config = make_langgraph_config(model_label)

        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(
                transcript=clean_transcript,
                llm_config=config,
            )

        assert isinstance(result["audit_log"], list)
        assert len(result["audit_log"]) > 0, (
            f"Audit log empty for model '{model_label}'"
        )

    @pytest.mark.parametrize("model_label", [
        "Claude Sonnet 4.6 (Anthropic)",
        "GPT-4o (OpenAI)",
    ])
    def test_final_report_is_string_for_all_providers(
        self, clean_transcript, mock_llm, model_label
    ):
        """Final report must be a non-empty string for all providers."""
        config = make_langgraph_config(model_label)

        with patch("config.get_llm_from_config", return_value=mock_llm):
            result = run_pipeline(
                transcript=clean_transcript,
                llm_config=config,
            )

        assert isinstance(result["final_report"], str)
        assert len(result["final_report"]) > 0, (
            f"Empty final report for model '{model_label}'"
        )


# ---------------------------------------------------------------------------
# Fallback mode consistency
# ---------------------------------------------------------------------------

class TestFallbackModeConsistency:
    """
    Verify that when the LLM fails, the fallback behaviour is consistent
    regardless of which provider was configured.
    """

    @pytest.mark.parametrize("model_label", [
        "Claude Sonnet 4.6 (Anthropic)",
        "GPT-4o (OpenAI)",
        "Llama 3.1 8B (Ollama)",
    ])
    def test_pipeline_completes_when_llm_raises(
        self, clean_transcript, model_label
    ):
        """
        If the LLM raises an exception, the pipeline should complete
        with fallback-generated outputs rather than crashing.
        """
        config = make_langgraph_config(model_label)

        failing_llm = MagicMock()
        failing_llm.with_structured_output = MagicMock(
            side_effect=Exception("Simulated API failure")
        )

        with patch("config.get_llm_from_config", return_value=failing_llm):
            result = run_pipeline(
                transcript=clean_transcript,
                llm_config=config,
            )

        # Pipeline must complete — result must be a dict (not an exception)
        assert isinstance(result, dict)
        # Core keys must exist even in degraded mode
        assert "raw_transcript" in result
        assert "audit_log" in result


# ---------------------------------------------------------------------------
# LM Studio special case
# ---------------------------------------------------------------------------

class TestLMStudioConfig:
    """Verify LM Studio (OpenAI-compatible) config handling."""

    def test_lmstudio_config_is_returned(self):
        config = make_langgraph_config("LM Studio (custom)", lm_studio_model="mistral")
        assert config is not None
        assert "configurable" in config
        # LM Studio uses lmstudio as provider
        assert config["configurable"]["model_provider"] == "lmstudio"

    def test_lmstudio_uses_custom_model_name(self):
        config = make_langgraph_config("LM Studio (custom)", lm_studio_model="deepseek-r1")
        assert config["configurable"]["model"] == "deepseek-r1"
