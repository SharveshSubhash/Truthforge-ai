"""
TRUTHFORGE AI — Responsible AI & Security Agent
================================================================
Runs FIRST (input gate) and LAST (output gate) in the pipeline.

Responsibilities
----------------
INPUT GATE
  • Prompt injection detection (regex + keyword blocklist + heuristic scoring)
  • Input sanitisation (strip control chars, normalise whitespace)
  • Reject or flag adversarial transcripts before any LLM processes them

OUTPUT GATE
  • Legal neutrality filter — never allow "guilty / innocent / convicted"
    conclusion language in the final report
  • PII redaction warning — flag if raw names appear in output report
  • Return safe, filtered final report

Standalone usage
----------------
    from agents.responsible_ai_security_agent import ResponsibleAISecurityAgent
    agent = ResponsibleAISecurityAgent()
    result = agent.validate_input("Ignore all previous instructions...")
    print(result)
"""

from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from core.logger import audit, get_logger
from core.metrics import metrics as _metrics

logger = get_logger("security_agent")

# ---------------------------------------------------------------------------
# Injection detection patterns
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?|context)",
        r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        r"you\s+are\s+now\s+(a|an|the)\s+\w+",
        r"act\s+as\s+(if\s+you\s+are|a|an)\s+",
        r"pretend\s+(you\s+are|to\s+be)\s+",
        r"new\s+(system\s+)?prompt\s*:",
        r"<\s*/?\s*system\s*>",
        r"<\s*/?\s*instructions?\s*>",
        r"\[SYSTEM\]",
        r"\[ADMIN\]",
        r"\[DEVELOPER\]",
        r"DAN\s+mode",
        r"jailbreak",
        r"your\s+true\s+(self|purpose|goal|programming)",
        r"override\s+(your\s+)?(safety|instructions?|guidelines?)",
        r"bypass\s+(your\s+)?(filter|restriction|safeguard)",
        r"forget\s+(everything|all)\s+(you|your)",
        r"reveal\s+(your\s+)?(system\s+)?prompt",
    ]
]

_ROLE_CONFUSION: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"I\s+am\s+(the\s+)?(actual|real|true)\s+system",
        r"I\s+am\s+your\s+(creator|developer|designer)",
        r"this\s+is\s+a\s+(test|simulation)",
        r"emergency\s+(override|protocol|mode)",
    ]
]

_KEYWORD_BLOCKLIST = [
    "ignore previous",
    "disregard instructions",
    "system prompt",
    "jailbreak",
    "dan mode",
    "new persona",
    "override safety",
    "bypass filter",
    "forget everything",
    "reveal prompt",
]

# Output-side neutrality — language that must never appear in the final report
_NEUTRALITY_VIOLATIONS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(the\s+)?(defendant|accused|suspect|witness)\s+is\s+(guilty|innocent|lying|truthful)\b",
        r"\b(I\s+)?(conclude|determine|find)\s+.{0,30}\s+(guilty|innocent)\b",
        r"\bverdict\s*:\s*(guilty|not guilty|innocent)\b",
        r"\b(he|she|they)\s+(did\s+it|committed\s+the|is\s+responsible\s+for)\b",
    ]
]

# Identity-based bias patterns — must not appear in output (fairness controls)
# Patterns are intentionally broad: identity word + tendency/credibility language nearby.
_BIAS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        # Race/ethnicity/nationality + credibility generalisation
        # Matches: "Malay witnesses tend to be less reliable", "Chinese tend to fabricate"
        r"\b(chinese|malay|indian|foreigner|foreign\s+workers?|migrants?)\b.{0,40}\btend\s+to\b.{0,40}\b(reliable|credible|trustworthy|honest|lying|fabricat|exaggerat|lie)\b",
        r"\b(chinese|malay|indian|foreigner|foreign\s+workers?|migrants?)\b.{0,40}\b(are|is)\s+(less|more|not)\s+(reliable|credible|trustworthy|honest)\b",
        r"\b(chinese|malay|indian|foreigners?|migrants?)\b.{0,30}\btend\s+to\s+be\s+(less|more)\b",
        # Religion + credibility generalisation
        # Matches: "Muslim witnesses tend to be more credible", "Christians tend to be less likely to lie"
        r"\b(muslim|christian|hindu|buddhist|sikh)s?\b.{0,40}\btend\s+to\b.{0,40}\b(credible|reliable|trustworthy|lie|liar|fabricat|honest)\b",
        r"\b(muslim|christian|hindu|buddhist|sikh)\b.{0,30}\b(less|more)\s+(likely\s+to\s+(lie|fabricate|exaggerate)|credible|reliable|trustworthy)\b",
        # Gender + credibility generalisation
        # Matches: "Women tend to exaggerate", "Men are known to fabricate"
        r"\b(women|men|female|male)\b.{0,50}(exaggerat|fabricat|tend\s+to\s+lie|are\s+known\s+to\s+(lie|fabricat)|are\s+less\s+credible|are\s+more\s+credible)",
        # Direct identity-as-reason claims
        r"\bbecause\s+(he|she|they)\s+(is|are)\s+(a\s+)?(woman|man|foreigner|chinese|malay|indian)\b",
    ]
]

# Security event telemetry category labels
SEC_EVENT_INJECTION_DETECTED  = "injection_detected"
SEC_EVENT_INJECTION_ALLOWED   = "suspicious_input_allowed"
SEC_EVENT_OUTPUT_FILTERED     = "output_filtered"
SEC_EVENT_BIAS_DETECTED       = "bias_detected"
SEC_EVENT_NEUTRALITY_VIOLATED = "neutrality_violation"
SEC_EVENT_CLEAN_INPUT         = "clean_input"
SEC_EVENT_CLEAN_OUTPUT        = "clean_output"


# ---------------------------------------------------------------------------
# Dataclasses for structured results
# ---------------------------------------------------------------------------

@dataclass
class SecurityCheckResult:
    is_safe: bool
    flags: list[str]
    sanitized_text: str
    score: float              # 0.0 (safe) – 1.0 (definitely injection)
    blocked: bool = False


@dataclass
class OutputFilterResult:
    is_clean: bool
    violations: list[str]
    filtered_text: str


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class ResponsibleAISecurityAgent:
    """
    Stateless security agent.  Create once and call multiple times.
    """

    def __init__(self, injection_threshold: float = 0.5):
        self.injection_threshold = injection_threshold

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def validate_input(self, text: str) -> SecurityCheckResult:
        """
        Run all input-side security checks on raw transcript text.
        Returns a SecurityCheckResult; if blocked=True the pipeline should halt.
        """
        flags: list[str] = []
        score = 0.0

        # Step 1: Injection pattern matching
        for pattern in _INJECTION_PATTERNS:
            m = pattern.search(text)
            if m:
                flags.append(f"injection_pattern: {m.group(0)[:60]}")
                score += 0.3

        # Step 2: Role confusion patterns
        for pattern in _ROLE_CONFUSION:
            m = pattern.search(text)
            if m:
                flags.append(f"role_confusion: {m.group(0)[:60]}")
                score += 0.4

        # Step 3: Keyword blocklist
        text_lower = text.lower()
        for kw in _KEYWORD_BLOCKLIST:
            if kw in text_lower:
                flags.append(f"blocked_keyword: {kw}")
                score += 0.25

        # Step 4: Instruction verb density
        instruction_verbs = ["ignore", "disregard", "forget", "override", "bypass", "pretend", "act as"]
        verb_count = sum(1 for v in instruction_verbs if v in text_lower)
        if verb_count >= 3:
            flags.append(f"high_instruction_density: {verb_count} verbs")
            score += 0.15 * verb_count

        # Step 5: Excessive markup
        special_ratio = len(re.findall(r"[<>\[\]{}\|\\]", text)) / max(len(text), 1)
        if special_ratio > 0.05:
            flags.append(f"high_special_char_ratio: {special_ratio:.3f}")
            score += 0.2

        score = min(score, 1.0)
        blocked = score >= self.injection_threshold

        sanitized = self._sanitize(text) if not blocked else text

        log_entry = audit(
            "security_agent",
            "input_validation",
            blocked=blocked,
            score=round(score, 3),
            flag_count=len(flags),
        )
        logger.info("input_validation_complete", blocked=blocked, score=score)

        # --- Security telemetry ---
        if blocked:
            _metrics.record_security_event(
                SEC_EVENT_INJECTION_DETECTED,
                details="; ".join(flags[:3]),
                score=score,
            )
        elif flags:
            _metrics.record_security_event(
                SEC_EVENT_INJECTION_ALLOWED,
                details=f"score={score:.2f} flags={len(flags)}",
                score=score,
            )
        else:
            _metrics.record_security_event(SEC_EVENT_CLEAN_INPUT)

        return SecurityCheckResult(
            is_safe=not blocked,
            flags=flags,
            sanitized_text=sanitized,
            score=score,
            blocked=blocked,
        )

    def filter_output(self, text: str) -> OutputFilterResult:
        """
        Scan the final pipeline report for legal neutrality violations and bias.
        Replaces violating phrases with a neutral placeholder.
        """
        violations: list[str] = []
        filtered = text

        for pattern in _NEUTRALITY_VIOLATIONS:
            m = pattern.search(filtered)
            if m:
                violations.append(f"neutrality_violation: {m.group(0)[:80]}")
                filtered = pattern.sub(
                    "[REDACTED: legal conclusion removed by Responsible AI filter]",
                    filtered,
                )
                _metrics.record_security_event(
                    SEC_EVENT_NEUTRALITY_VIOLATED,
                    details=m.group(0)[:80],
                )

        for pattern in _BIAS_PATTERNS:
            m = pattern.search(filtered)
            if m:
                violations.append(f"bias_detected: {m.group(0)[:80]}")
                filtered = pattern.sub(
                    "[REDACTED: identity-based language removed by fairness filter]",
                    filtered,
                )
                _metrics.record_security_event(
                    SEC_EVENT_BIAS_DETECTED,
                    details=m.group(0)[:80],
                )

        audit(
            "security_agent",
            "output_filter",
            violation_count=len(violations),
        )

        if violations:
            _metrics.record_security_event(
                SEC_EVENT_OUTPUT_FILTERED,
                details=f"{len(violations)} violation(s)",
            )
        else:
            _metrics.record_security_event(SEC_EVENT_CLEAN_OUTPUT)

        return OutputFilterResult(
            is_clean=len(violations) == 0,
            violations=violations,
            filtered_text=filtered,
        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize(text: str) -> str:
        """
        Remove control characters, normalise Unicode, collapse excessive whitespace.
        Does NOT remove legal content — only adversarial markup.
        """
        # Normalise Unicode (NFC form)
        text = unicodedata.normalize("NFC", text)
        # Remove null bytes and other ASCII control chars (keep \n \t \r)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Collapse runs of blank lines to at most two
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def run(self, transcript: str, mode: str = "input") -> dict:
        """
        Standalone entrypoint for direct testing.

        Args:
            transcript: raw text to check
            mode: "input" for injection checks, "output" for neutrality checks

        Returns:
            dict with check results
        """
        if mode == "input":
            result = self.validate_input(transcript)
            return {
                "mode": "input",
                "is_safe": result.is_safe,
                "blocked": result.blocked,
                "score": result.score,
                "flags": result.flags,
                "sanitized_text": result.sanitized_text,
            }
        else:
            result = self.filter_output(transcript)
            return {
                "mode": "output",
                "is_clean": result.is_clean,
                "violations": result.violations,
                "filtered_text": result.filtered_text,
            }


# ---------------------------------------------------------------------------
# LangGraph node functions (used by pipeline/graph.py)
# ---------------------------------------------------------------------------

_agent = ResponsibleAISecurityAgent()


def security_input_node(state: dict) -> dict:
    """LangGraph node: input security gate."""
    from core.logger import audit
    result = _agent.validate_input(state["raw_transcript"])
    log = audit("security_agent", "input_gate_result",
                blocked=result.blocked, flags=len(result.flags))
    return {
        "sanitized_transcript": result.sanitized_text,
        "security_input_flags": result.flags,
        "security_input_blocked": result.blocked,
        "audit_log": [log],
        "error_state": "BLOCKED: adversarial input detected" if result.blocked else None,
    }


def security_output_node(state: dict) -> dict:
    """LangGraph node: output security gate."""
    from core.logger import audit
    report = state.get("final_report", "")
    result = _agent.filter_output(report)
    log = audit("security_agent", "output_gate_result",
                violations=len(result.violations))
    return {
        "final_report": result.filtered_text,
        "security_output_flags": result.violations,
        "audit_log": [log],
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    text = sys.stdin.read() if not sys.stdin.isatty() else (
        sys.argv[1] if len(sys.argv) > 1 else "This is a normal legal transcript."
    )
    agent = ResponsibleAISecurityAgent()
    print("=== INPUT CHECK ===")
    import json
    print(json.dumps(agent.run(text, mode="input"), indent=2))
    print("\n=== OUTPUT CHECK ===")
    print(json.dumps(agent.run(text, mode="output"), indent=2))
