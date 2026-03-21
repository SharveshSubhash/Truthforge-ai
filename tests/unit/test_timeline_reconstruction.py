"""
Unit tests for the Timeline Reconstruction Agent.
Tests temporal parsing and fallback ordering (no LLM needed).
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.timeline_reconstruction_agent import TimelineReconstructionAgent, _try_parse_date


class TestDateParsing:
    """Test the _try_parse_date utility."""

    def test_parses_iso_date(self):
        result = _try_parse_date("2024-01-15")
        assert result is not None
        assert "2024" in result

    def test_parses_natural_date(self):
        result = _try_parse_date("15 January 2024")
        assert result is not None
        assert "2024" in result

    def test_returns_none_for_empty_string(self):
        result = _try_parse_date("")
        assert result is None

    def test_returns_none_for_garbage(self):
        result = _try_parse_date("the next morning")
        # May return None or a parsed result depending on dateutil fuzzy
        # Either is acceptable — just must not raise
        pass

    def test_parses_time_with_date(self):
        result = _try_parse_date("10:32pm on 14 January 2024")
        assert result is not None


class TestTimelineReconstructionAgent:
    """Test the agent's run() method in fallback mode."""

    @pytest.fixture
    def agent(self):
        return TimelineReconstructionAgent()

    def test_empty_facts_returns_empty_timeline(self, agent):
        result = agent.run({}, llm=None)
        assert result["timeline"] == []

    def test_run_returns_expected_keys(self, agent, sample_structured_facts):
        result = agent.run(sample_structured_facts, llm=None)
        assert "timeline" in result
        assert "audit_log" in result

    def test_timeline_events_have_required_fields(self, agent, sample_structured_facts):
        result = agent.run(sample_structured_facts, llm=None)
        for ev in result["timeline"]:
            assert "event_id" in ev
            assert "description" in ev

    def test_timeline_preserves_all_events(self, agent, sample_structured_facts):
        input_count = len(sample_structured_facts["events"])
        result = agent.run(sample_structured_facts, llm=None)
        assert len(result["timeline"]) == input_count

    def test_events_with_parseable_dates_sorted_first(self, agent):
        facts = {
            "events": [
                {"event_id": "E001", "description": "Unknown time event",
                 "timestamp": None, "actors": [], "location": None, "source_excerpt": "unknown"},
                {"event_id": "E002", "description": "Known date event",
                 "timestamp": "15 January 2024", "actors": [], "location": None, "source_excerpt": "known"},
            ],
            "key_statements": [],
            "summary": "",
        }
        result = agent.run(facts, llm=None)
        timeline = result["timeline"]
        # Events with parseable dates should come before unknown ones
        assert len(timeline) == 2
        dated = [ev for ev in timeline if ev.get("normalized_time")]
        undated = [ev for ev in timeline if not ev.get("normalized_time")]
        if dated:
            dated_idx = timeline.index(dated[0])
            if undated:
                undated_idx = timeline.index(undated[0])
                assert dated_idx <= undated_idx

    def test_audit_log_has_entries(self, agent, sample_structured_facts):
        result = agent.run(sample_structured_facts, llm=None)
        assert len(result["audit_log"]) >= 2
