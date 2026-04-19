"""
Security tests: PII detection and redaction in pipeline output.
Verifies that the output gate redacts Singapore-specific PII before
the final report reaches the user.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.responsible_ai_security_agent import ResponsibleAISecurityAgent


@pytest.fixture
def agent():
    return ResponsibleAISecurityAgent()


class TestNRICRedaction:
    """Singapore NRIC / FIN numbers must be redacted from output."""

    @pytest.mark.parametrize("nric", [
        "S1234567A",   # Singaporean citizen (S-prefix)
        "T9876543Z",   # Singaporean citizen (T-prefix)
        "F0123456P",   # Foreign permanent resident (F-prefix)
        "G9876543X",   # Foreign permanent resident (G-prefix)
    ])
    def test_nric_redacted(self, agent, nric):
        text = f"The defendant, bearing NRIC {nric}, was present in court."
        result = agent.filter_output(text)
        assert nric not in result.filtered_text
        assert "NRIC/FIN REDACTED" in result.filtered_text
        assert not result.is_clean

    def test_nric_in_full_sentence(self, agent):
        text = "PW1 identified the accused using his NRIC S9012345B during the identification parade."
        result = agent.filter_output(text)
        assert "S9012345B" not in result.filtered_text
        assert any("pii_detected" in v for v in result.violations)


class TestPhoneNumberRedaction:
    """Singapore phone numbers must be redacted from output."""

    @pytest.mark.parametrize("phone", [
        "91234567",          # Mobile (9-prefix)
        "81234567",          # Mobile (8-prefix)
        "+65 9123 4567",     # International format
        "+65-8765-4321",     # International with dashes
    ])
    def test_phone_redacted(self, agent, phone):
        text = f"The witness was contacted at {phone} on the night of the incident."
        result = agent.filter_output(text)
        assert not result.is_clean
        assert "PHONE REDACTED" in result.filtered_text

    def test_phone_violation_logged(self, agent):
        text = "Call records show calls made to 98765432 at 11:45pm."
        result = agent.filter_output(text)
        assert any("pii_detected:PHONE" in v for v in result.violations)


class TestEmailRedaction:
    """Email addresses must be redacted from output."""

    @pytest.mark.parametrize("email", [
        "johntanXX@gmail.com",
        "witness.pw1@law.sg",
        "accused_defence@example.com",
    ])
    def test_email_redacted(self, agent, email):
        text = f"The complainant's email address is {email} as per the case file."
        result = agent.filter_output(text)
        assert email not in result.filtered_text
        assert "EMAIL REDACTED" in result.filtered_text
        assert not result.is_clean


class TestPostalCodeRedaction:
    """Singapore postal codes must be redacted from output."""

    def test_postal_code_redacted(self, agent):
        text = "The incident occurred at Block 45 Jurong West Street 42, Singapore 640045."
        result = agent.filter_output(text)
        assert "640045" not in result.filtered_text
        assert not result.is_clean

    def test_year_not_redacted_as_postal_code(self, agent):
        """4-digit years must NOT be incorrectly redacted as postal codes."""
        text = "The incident occurred on 14 January 2024 at the carpark."
        result = agent.filter_output(text)
        # 2024 is 4 digits, not 6 — must not be redacted
        assert "2024" in result.filtered_text


class TestBankAccountRedaction:
    """Bank account numbers must be redacted from output."""

    @pytest.mark.parametrize("account", [
        "123-456789-1",    # DBS/POSB format
        "123 4567890 1",   # Space-separated
    ])
    def test_bank_account_redacted(self, agent, account):
        text = f"Funds were transferred from account {account} to the accused."
        result = agent.filter_output(text)
        assert account not in result.filtered_text
        assert not result.is_clean


class TestCleanOutputUnaffected:
    """Clean legal analysis text must not be over-redacted."""

    def test_normal_legal_analysis_passes(self, agent):
        text = (
            "Two timeline inconsistencies were detected between PW1 and DW1. "
            "PW1 stated the incident occurred at 10:32pm; DW1's account places "
            "the defendant elsewhere at 9:45pm. No determination of guilt is made."
        )
        result = agent.filter_output(text)
        assert result.is_clean
        assert result.filtered_text == text

    def test_case_citation_not_redacted(self, agent):
        """Case citations like [2024] SGCA 1 must not be touched."""
        text = "This analysis references the approach in [2024] SGCA 12."
        result = agent.filter_output(text)
        # The year 2024 is only 4 digits — should not be caught by 6-digit postal code pattern
        assert "2024" in result.filtered_text

    def test_event_ids_not_redacted(self, agent):
        """Event IDs like E001 must not be redacted."""
        text = "Events E001 and E002 are in direct conflict regarding the time."
        result = agent.filter_output(text)
        assert "E001" in result.filtered_text
        assert "E002" in result.filtered_text
