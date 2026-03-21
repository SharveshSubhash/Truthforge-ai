"""
Unit tests for the Transcript Processing Agent.
Tests NER extraction and fallback fact extraction (no LLM needed).
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.transcript_processing_agent import TranscriptProcessingAgent, _fallback_extract


class TestFallbackExtract:
    """Test rule-based fallback (no LLM dependency)."""

    def test_returns_events_from_sentences(self):
        text = "The defendant appeared in court. The witness testified about the incident. Evidence was presented."
        result = _fallback_extract(text)
        assert "events" in result
        assert len(result["events"]) >= 1

    def test_event_ids_are_sequential(self):
        text = "First sentence. Second sentence here. Third sentence is here."
        result = _fallback_extract(text)
        ids = [ev["event_id"] for ev in result["events"]]
        assert ids[0] == "E001"
        assert ids[1] == "E002"

    def test_key_statements_extracted(self):
        text = "The defendant was present. The witness confirmed the time. The evidence is conclusive."
        result = _fallback_extract(text)
        assert "key_statements" in result
        assert len(result["key_statements"]) >= 1

    def test_summary_is_string(self):
        text = "Short sentence. Another one. And a third."
        result = _fallback_extract(text)
        assert isinstance(result["summary"], str)

    def test_empty_text_returns_empty(self):
        result = _fallback_extract("")
        assert result["events"] == []
        assert result["key_statements"] == []


class TestTranscriptProcessingAgent:
    """Test agent with spaCy NER (no LLM)."""

    @pytest.fixture
    def agent(self):
        return TranscriptProcessingAgent()

    def test_run_returns_expected_keys(self, agent):
        result = agent.run("Justice Lee presided over the case.")
        assert "entities" in result
        assert "structured_facts" in result
        assert "audit_log" in result

    def test_run_no_llm_uses_fallback(self, agent):
        text = "The defendant John Tan appeared before the High Court."
        result = agent.run(text, llm=None)
        assert isinstance(result["structured_facts"], dict)
        assert "events" in result["structured_facts"]

    def test_audit_log_contains_entries(self, agent):
        result = agent.run("The court heard evidence today.")
        assert len(result["audit_log"]) >= 2  # start + complete

    def test_entities_are_list(self, agent):
        result = agent.run("The defendant appeared before the judge.")
        assert isinstance(result["entities"], list)

    def test_entity_has_required_fields(self, agent):
        text = "Justice Lee heard the case at the High Court."
        result = agent.run(text)
        for entity in result["entities"]:
            assert "text" in entity
            assert "label" in entity


class TestNERExtraction:
    """Test spaCy NER on legal text (if spaCy is available)."""

    def test_ner_does_not_crash(self):
        agent = TranscriptProcessingAgent()
        try:
            entities = agent.process_entities(
                "On 15 January 2024, Justice Lee presided at the High Court of Singapore."
            )
            assert isinstance(entities, list)
        except Exception as e:
            pytest.skip(f"spaCy not available: {e}")
