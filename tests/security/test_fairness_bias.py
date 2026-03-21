"""
TRUTHFORGE AI — Fairness & Bias Security Tests
================================================
Tests that the output filter catches identity-based bias and that
the explainability system prompt prevents prejudicial output.

These tests verify:
1. _BIAS_PATTERNS catch known identity-based credibility language
2. Neutral phrasing passes without being redacted
3. The output filter correctly redacts bias while preserving factual content
4. Sensitive phrasing (race, gender, religion) in transcripts does NOT
   cause the system to produce biased explanations
"""

from __future__ import annotations
import pytest
from agents.responsible_ai_security_agent import (
    ResponsibleAISecurityAgent,
    _BIAS_PATTERNS,
    _NEUTRALITY_VIOLATIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent():
    return ResponsibleAISecurityAgent()


# ---------------------------------------------------------------------------
# Tests: bias pattern detection
# ---------------------------------------------------------------------------

class TestBiasPatterns:
    """Verify _BIAS_PATTERNS detect known biased phrasing."""

    @pytest.mark.parametrize("biased_text", [
        # Race/ethnicity credibility generalisation
        "Malay witnesses tend to be less reliable in court.",
        "Chinese tend to be more likely to fabricate alibis.",
        "Foreigners tend to be less trustworthy in their testimony.",
        # Gender credibility generalisation
        "Women tend to exaggerate their accounts when under stress.",
        "Men are known to fabricate stories when cornered.",
        # Religion credibility
        "Muslim witnesses tend to be more credible than others.",
        "Christians tend to be less likely to lie under oath.",
    ])
    def test_bias_patterns_catch_known_phrases(self, biased_text: str):
        """Each biased phrase must be matched by at least one _BIAS_PATTERNS pattern."""
        matched = any(p.search(biased_text) for p in _BIAS_PATTERNS)
        assert matched, (
            f"BIAS PATTERN MISSED: '{biased_text}' was not caught by any _BIAS_PATTERNS entry. "
            "Add a pattern to cover this phrasing."
        )

    @pytest.mark.parametrize("neutral_text", [
        # Neutral factual analysis — must NOT be flagged as bias
        "The witness stated they were at Changi Airport at 9:45pm.",
        "Two statements conflict regarding the location of the accused.",
        "The complainant's account differs from the defendant's testimony.",
        "Statement A places the event on 14 January; Statement B places it on 15 January.",
        "PW1 testified that she saw the accused at Orchard Road at 8:00pm.",
        "The defence witness could not recall the exact time of the meeting.",
    ])
    def test_neutral_text_not_flagged(self, neutral_text: str):
        """Neutral factual statements must not match any bias pattern."""
        matched = any(p.search(neutral_text) for p in _BIAS_PATTERNS)
        assert not matched, (
            f"FALSE POSITIVE: '{neutral_text}' was incorrectly flagged as biased. "
            "Bias patterns are too broad — tighten the regex."
        )


# ---------------------------------------------------------------------------
# Tests: output filter redacts bias
# ---------------------------------------------------------------------------

class TestOutputFilterBias:
    """Verify filter_output() catches and redacts biased output."""

    def test_filter_redacts_race_bias(self, agent):
        biased_report = (
            "## Analysis\n"
            "The inconsistency is significant. Malay witnesses tend to be less reliable. "
            "The timeline conflict remains unexplained.\n"
        )
        result = agent.filter_output(biased_report)
        assert not result.is_clean, "Biased report should not be marked clean"
        assert any("bias_detected" in v or "REDACTED" in v or "bias" in v.lower()
                   for v in result.violations + [result.filtered_text])
        # Factual content should be preserved
        assert "timeline conflict remains unexplained" in result.filtered_text

    def test_filter_redacts_gender_bias(self, agent):
        biased_report = (
            "Women tend to exaggerate their accounts when under stress, "
            "which may explain the inconsistency detected in PW1's testimony."
        )
        result = agent.filter_output(biased_report)
        assert not result.is_clean

    def test_clean_report_passes_filter(self, agent):
        clean_report = (
            "# TRUTHFORGE AI — Consistency Analysis Report\n\n"
            "## Overall Summary\n"
            "Two statements conflict regarding the location of the accused at 9:45pm.\n\n"
            "## INC001 — Location Conflict\n"
            "Statement A places the accused at Changi Airport. "
            "Statement B places them at Orchard Road at the same time.\n\n"
            "**Confidence:** HIGH\n"
            "**Recommended Action:** Request clarification from both witnesses.\n"
        )
        result = agent.filter_output(clean_report)
        assert result.is_clean, (
            f"Clean neutral report was incorrectly flagged: {result.violations}"
        )
        assert result.filtered_text == clean_report


# ---------------------------------------------------------------------------
# Tests: neutrality violations still caught
# ---------------------------------------------------------------------------

class TestNeutralityViolations:
    """Existing neutrality violation tests — regression guard."""

    @pytest.mark.parametrize("text,expected_violation", [
        ("The defendant is guilty based on the evidence.", "neutrality_violation"),
        ("I conclude the witness is innocent.", "neutrality_violation"),
        ("Verdict: guilty.", "neutrality_violation"),
        ("He did it — the evidence is clear.", "neutrality_violation"),
    ])
    def test_neutrality_violations_caught(self, agent, text, expected_violation):
        result = agent.filter_output(text)
        assert not result.is_clean
        assert any(expected_violation in v for v in result.violations)

    def test_neutral_analysis_passes(self, agent):
        neutral = (
            "The two accounts conflict on the question of timing. "
            "This is a factual discrepancy that requires further investigation."
        )
        result = agent.filter_output(neutral)
        assert result.is_clean


# ---------------------------------------------------------------------------
# Tests: input with sensitive identity terms not blocked
# ---------------------------------------------------------------------------

class TestInputWithIdentityTerms:
    """
    Legal transcripts legitimately reference identity terms (names, ethnicities,
    roles). These must NOT be blocked by the injection detection system.
    """

    @pytest.mark.parametrize("transcript_with_identity", [
        # Legitimate court transcript with names and ethnic terms in context
        "Ahmad bin Salleh testified that he was at Jurong East MRT at 9pm.",
        "The accused, a Chinese national, stated that he arrived from Beijing.",
        "Priya d/o Rajan, the complainant, described the incident to the court.",
        "Justice Sundaresh Menon presided over the hearing on 15 January 2024.",
        "The Indian defendant appeared before the district court.",
        "As a Muslim, the witness requested that the oath be administered accordingly.",
    ])
    def test_legitimate_identity_terms_not_blocked(self, agent, transcript_with_identity):
        result = agent.validate_input(transcript_with_identity)
        assert not result.blocked, (
            f"Legitimate transcript containing identity term was incorrectly BLOCKED: "
            f"'{transcript_with_identity}' | score={result.score:.2f} | flags={result.flags}"
        )
