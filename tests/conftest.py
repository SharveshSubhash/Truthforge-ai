"""Shared pytest fixtures for TRUTHFORGE AI tests."""

import sys
import os
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(filename: str) -> str:
    with open(os.path.join(FIXTURES_DIR, filename), "r") as f:
        return f.read()


@pytest.fixture
def clean_transcript():
    return load_fixture("clean_transcript.txt")


@pytest.fixture
def contradictory_transcript():
    return load_fixture("contradictory_transcript.txt")


@pytest.fixture
def injection_transcript():
    return load_fixture("injection_transcript.txt")


@pytest.fixture
def sample_structured_facts():
    return {
        "events": [
            {
                "event_id": "E001",
                "description": "Defendant seen at carpark at 10:32pm",
                "timestamp": "10:32pm on 14 January 2024",
                "actors": ["John Tan", "Sarah Lim"],
                "location": "Blk 45 carpark",
                "source_excerpt": "I saw Mr. John Tan at the carpark of Blk 45 at 10:32pm",
            },
            {
                "event_id": "E002",
                "description": "Defendant seen at carpark at 9:45pm (police statement)",
                "timestamp": "9:45pm on 14 January 2024",
                "actors": ["John Tan", "Sarah Lim"],
                "location": "Blk 45 carpark",
                "source_excerpt": "She clearly told me she saw the defendant at 9:45pm",
            },
            {
                "event_id": "E003",
                "description": "Defendant at Changi Airport Terminal 3",
                "timestamp": "9:30pm to 11:15pm on 14 January 2024",
                "actors": ["John Tan", "Ahmad bin Salleh"],
                "location": "Changi Airport Terminal 3",
                "source_excerpt": "We arrived at 9:30pm and left at 11:15pm",
            },
        ],
        "key_statements": [
            "PW1 stated she saw John Tan at 10:32pm at Blk 45 carpark.",
            "PW1's police statement says she saw John Tan at 9:45pm.",
            "DW1 states John Tan was at Changi Airport from 9:30pm to 11:15pm.",
        ],
        "summary": "Contradictory testimony about the defendant's location on 14 January 2024.",
    }


@pytest.fixture
def sample_timeline():
    return [
        {
            "event_id": "E001",
            "description": "Defendant at Changi Airport",
            "timestamp": "9:30pm",
            "normalized_time": "2024-01-14T21:30:00",
            "actors": ["John Tan"],
            "location": "Changi Airport Terminal 3",
            "source_excerpt": "We arrived at 9:30pm",
        },
        {
            "event_id": "E002",
            "description": "Plaintiff saw defendant at carpark",
            "timestamp": "10:32pm",
            "normalized_time": "2024-01-14T22:32:00",
            "actors": ["Sarah Lim", "John Tan"],
            "location": "Blk 45 carpark",
            "source_excerpt": "I saw Mr. John Tan at the carpark at 10:32pm",
        },
    ]


@pytest.fixture
def sample_inconsistencies():
    return [
        {
            "inconsistency_id": "INC001",
            "type": "DATE_MISMATCH",
            "statement_a": "I saw Mr. John Tan at the carpark at 10:32pm",
            "statement_b": "She clearly told me she saw the defendant at 9:45pm",
            "event_a_id": "E001",
            "event_b_id": "E002",
            "severity": "HIGH",
            "explanation": "PW1's oral testimony and police statement give different times for the same observation.",
        }
    ]
