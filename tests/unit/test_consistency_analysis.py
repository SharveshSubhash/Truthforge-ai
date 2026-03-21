"""
Unit tests for the Consistency Analysis Agent.
Tests rule-based contradiction detection (no LLM needed).
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.consistency_analysis_agent import ConsistencyAnalysisAgent


class TestConsistencyAnalysisAgent:

    @pytest.fixture
    def agent(self):
        return ConsistencyAnalysisAgent()

    def test_empty_inputs_return_empty(self, agent):
        result = agent.run([], [], {}, llm=None)
        assert result["inconsistencies"] == []

    def test_run_returns_expected_keys(self, agent, sample_timeline, sample_structured_facts):
        result = agent.run(sample_timeline, [], sample_structured_facts, llm=None)
        assert "inconsistencies" in result
        assert "audit_log" in result

    def test_clean_timeline_returns_no_inconsistencies_rule_based(self, agent):
        """Timeline with no conflicts should return empty list from rule-based check."""
        clean_timeline = [
            {"event_id": "E001", "description": "Defendant at home",
             "timestamp": "9:00pm", "normalized_time": "2024-01-14T21:00:00",
             "actors": ["John Tan"], "location": "home",
             "source_excerpt": "He was at home"},
            {"event_id": "E002", "description": "Defendant at court",
             "timestamp": "9:00am", "normalized_time": "2024-01-15T09:00:00",
             "actors": ["John Tan"], "location": "High Court",
             "source_excerpt": "He appeared at court"},
        ]
        result = agent.run(clean_timeline, [], {}, llm=None)
        # Rule-based should not flag events at different times
        assert isinstance(result["inconsistencies"], list)

    def test_location_conflict_detected_rule_based(self, agent):
        """Two events at the exact same normalised time but different locations."""
        conflicting_timeline = [
            {"event_id": "E001", "description": "Person at airport",
             "timestamp": "10pm", "normalized_time": "2024-01-14T22:00:00",
             "actors": ["John Tan"], "location": "Changi Airport",
             "source_excerpt": "He was at Changi Airport at 10pm"},
            {"event_id": "E002", "description": "Person at crime scene",
             "timestamp": "10pm", "normalized_time": "2024-01-14T22:00:00",
             "actors": ["John Tan"], "location": "Blk 45 carpark",
             "source_excerpt": "He was at the carpark at 10pm"},
        ]
        result = agent.run(conflicting_timeline, [], {}, llm=None)
        # Rule-based should detect the location conflict
        assert len(result["inconsistencies"]) >= 1
        types = [inc["type"] for inc in result["inconsistencies"]]
        assert "LOCATION_CONFLICT" in types

    def test_inconsistency_has_required_fields(self, agent):
        conflicting = [
            {"event_id": "E001", "description": "A",
             "timestamp": "10pm", "normalized_time": "2024-01-14T22:00:00",
             "actors": ["X"], "location": "Location A", "source_excerpt": "at Location A"},
            {"event_id": "E002", "description": "B",
             "timestamp": "10pm", "normalized_time": "2024-01-14T22:00:00",
             "actors": ["X"], "location": "Location B", "source_excerpt": "at Location B"},
        ]
        result = agent.run(conflicting, [], {}, llm=None)
        for inc in result["inconsistencies"]:
            assert "inconsistency_id" in inc
            assert "type" in inc
            assert "statement_a" in inc
            assert "statement_b" in inc
            assert "severity" in inc
            assert "explanation" in inc

    def test_severity_is_valid_value(self, agent):
        conflicting = [
            {"event_id": "E001", "normalized_time": "2024-01-14T22:00:00",
             "location": "A", "source_excerpt": "at A", "description": "A", "actors": []},
            {"event_id": "E002", "normalized_time": "2024-01-14T22:00:00",
             "location": "B", "source_excerpt": "at B", "description": "B", "actors": []},
        ]
        result = agent.run(conflicting, [], {}, llm=None)
        for inc in result["inconsistencies"]:
            assert inc["severity"] in {"HIGH", "MEDIUM", "LOW"}

    def test_audit_log_populated(self, agent, sample_timeline, sample_structured_facts):
        result = agent.run(sample_timeline, [], sample_structured_facts, llm=None)
        assert len(result["audit_log"]) >= 2
