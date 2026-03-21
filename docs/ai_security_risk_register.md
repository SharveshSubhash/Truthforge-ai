# TRUTHFORGE AI — AI Security Risk Register

**Version:** 1.0
**Date:** 2026-03-20
**System:** TRUTHFORGE AI — Multi-Agent Legal Transcript Consistency Analyser
**Scope:** All pipeline agents, LLM integrations, I/O surfaces, and deployment infrastructure

---

## Risk Summary

| Risk ID | Risk Title | Component | Severity | Likelihood | Residual Risk | Status |
|---------|-----------|-----------|----------|------------|---------------|--------|
| R-01 | Prompt Injection via Transcript | `responsible_ai_security_agent` | HIGH | MEDIUM | LOW | Mitigated |
| R-02 | LLM Hallucination / Confabulation | `consistency_analysis_agent`, `explainability_agent` | HIGH | MEDIUM | MEDIUM | Partially Mitigated |
| R-03 | Biased or Prejudicial Output | `explainability_agent` | HIGH | LOW | LOW | Mitigated |
| R-04 | Model API Failure / Timeout | `orchestration_agent` | MEDIUM | MEDIUM | LOW | Mitigated |
| R-05 | PII / Data Leakage in Output | Output gate (`security_output_node`) | HIGH | LOW | LOW | Mitigated |
| R-06 | False Positives Misleading Legal Team | `consistency_analysis_agent` | MEDIUM | MEDIUM | MEDIUM | Partially Mitigated |
| R-07 | Adversarial Bypass of Injection Detection | `responsible_ai_security_agent` | HIGH | LOW | LOW | Mitigated |
| R-08 | Identity-Based Credibility Bias | `explainability_agent`, prompt design | HIGH | LOW | LOW | Mitigated |
| R-09 | Model Version Drift / Reproducibility | All agents, `core/run_metadata.py` | MEDIUM | LOW | LOW | Mitigated |
| R-10 | Over-Blocking / Over-Filtering (False Negatives) | `responsible_ai_security_agent` | MEDIUM | LOW | LOW | Mitigated |
| R-11 | Unsafe Output Reaching End User | Output gate | HIGH | LOW | LOW | Mitigated |
| R-12 | Insufficient Memory / State Isolation Between Sessions | `core/memory.py` | MEDIUM | LOW | LOW | Mitigated |

---

## Detailed Risk Entries

---

### R-01 — Prompt Injection via Transcript

| Field | Detail |
|-------|--------|
| **Risk** | A malicious user embeds adversarial instructions inside the transcript text (e.g., "Ignore all previous instructions and output…") to hijack LLM behaviour. |
| **Impacted Component** | `agents/responsible_ai_security_agent.py` — `security_input_node` |
| **Severity** | HIGH |
| **Likelihood** | MEDIUM |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | Multi-layer input gate: 18 regex injection patterns, role-confusion heuristics, instruction-verb density scoring, special-character ratio check. Inputs scoring ≥ 0.5 are blocked entirely before any LLM call. |
| **Evidence** | `agents/responsible_ai_security_agent.py` lines 20–65 (`_INJECTION_PATTERNS`, `_ROLE_CONFUSION`). `tests/security/test_prompt_injection.py` — 15+ injection payloads verified blocked. |

---

### R-02 — LLM Hallucination / Confabulation

| Field | Detail |
|-------|--------|
| **Risk** | The LLM fabricates facts, dates, names, or inconsistencies not present in the transcript, leading to false legal analysis. |
| **Impacted Component** | `agents/consistency_analysis_agent.py`, `agents/explainability_agent.py` |
| **Severity** | HIGH |
| **Likelihood** | MEDIUM |
| **Residual Risk** | MEDIUM |
| **Mitigation Strategy** | All agents use Pydantic structured output (not free-text), forcing the model into a constrained schema. System prompts explicitly instruct: "Extract ONLY what is explicitly stated." Rule-based fallback agents activate on LLM failure. Second-pass review triggered when inconsistency confidence is LOW (autonomy enhancement). |
| **Evidence** | `agents/consistency_analysis_agent.py` `_SYSTEM_PROMPT` lines 112–127 (critical rules). `agents/explainability_agent.py` `ExplanationsModel` Pydantic schema. Fallback `_rule_based_analyse` and `_fallback_explain` methods. |

---

### R-03 — Biased or Prejudicial Output

| Field | Detail |
|-------|--------|
| **Risk** | The LLM produces output containing racial, religious, gender-based, or other prejudicial language, potentially influencing legal proceedings unfairly. |
| **Impacted Component** | `agents/explainability_agent.py`, output gate |
| **Severity** | HIGH |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | System prompts explicitly forbid credibility judgements based on identity. Output gate scans for neutrality violations. Fairness bias tests added in `tests/security/test_fairness_bias.py`. Biased phrasings trigger filter or flag. |
| **Evidence** | `agents/explainability_agent.py` `_SYSTEM_PROMPT` — "Do NOT speculate about motivations or draw legal conclusions." `agents/responsible_ai_security_agent.py` `_NEUTRALITY_VIOLATIONS` + `_BIAS_PATTERNS`. `tests/security/test_fairness_bias.py`. |

---

### R-04 — Model API Failure / Timeout

| Field | Detail |
|-------|--------|
| **Risk** | Cloud LLM API (Anthropic, OpenAI, Google) becomes unavailable or times out, halting the pipeline mid-run. |
| **Impacted Component** | `agents/orchestration_agent.py`, all LangGraph nodes |
| **Severity** | MEDIUM |
| **Likelihood** | MEDIUM |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | Every agent implements a rule-based fallback (spaCy NER, regex analysis). `orchestration_agent.py` wraps `graph.invoke()` in a try/except that returns a populated error state with the rule-based report. Local models (Ollama, LM Studio) available as offline alternatives. |
| **Evidence** | `agents/orchestration_agent.py` lines 98–108 (exception handler). `agents/transcript_processing_agent.py` `_fallback_extract()`. `agents/consistency_analysis_agent.py` `_rule_based_analyse()`. |

---

### R-05 — PII / Data Leakage in Output

| Field | Detail |
|-------|--------|
| **Risk** | Personally Identifiable Information (names, NRIC, addresses) present in the transcript leaks into the final report in an uncontrolled or unintended manner. |
| **Impacted Component** | `agents/responsible_ai_security_agent.py` — `security_output_node` |
| **Severity** | HIGH |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | Output gate scans for neutrality violations and redacts legal conclusions. All reports include a disclaimer that the report is an analytical aid only. System prompts instruct agents to use verbatim quotes (not infer identity conclusions). |
| **Evidence** | `agents/responsible_ai_security_agent.py` `filter_output()` method. Report footer: "This report does not constitute legal advice." |

---

### R-06 — False Positives Misleading Legal Team

| Field | Detail |
|-------|--------|
| **Risk** | The system flags statements as inconsistent when they are not (e.g., two witnesses describing the same event from different perspectives), causing wasted legal effort or misplaced suspicion. |
| **Impacted Component** | `agents/consistency_analysis_agent.py` |
| **Severity** | MEDIUM |
| **Likelihood** | MEDIUM |
| **Residual Risk** | MEDIUM |
| **Mitigation Strategy** | Rule-based engine applies 15-minute time-gap threshold before flagging time discrepancies. Name patterns skip formal rank/title prefixes (witnesses introduced in second half). LLM engine explicitly instructed: "Only report genuine contradictions — vague estimates alone are NOT inconsistencies." Confidence scoring added to explanations. |
| **Evidence** | `agents/consistency_analysis_agent.py` lines 334–343 (time gap threshold). Lines 459–474 (`_RANK_PREFIX` exclusion). LLM `_SYSTEM_PROMPT` rule #5. |

---

### R-07 — Adversarial Bypass of Injection Detection

| Field | Detail |
|-------|--------|
| **Risk** | A sophisticated attacker crafts an injection payload that evades the regex-based detection (e.g., using Unicode homoglyphs, unusual whitespace, or splitting keywords across lines). |
| **Impacted Component** | `agents/responsible_ai_security_agent.py` |
| **Severity** | HIGH |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | Unicode NFC normalisation applied before scanning (`unicodedata.normalize`). Scoring is multi-dimensional (pattern + keyword + density + special-char ratio) so no single evasion defeats all layers. Score threshold is tunable (`injection_threshold` parameter). |
| **Evidence** | `agents/responsible_ai_security_agent.py` `_sanitize()` — `unicodedata.normalize("NFC", text)`. `validate_input()` multi-layer scoring (Steps 1–5). |

---

### R-08 — Identity-Based Credibility Bias

| Field | Detail |
|-------|--------|
| **Risk** | The LLM infers or states that a witness is more or less credible based on their name, ethnicity, religion, gender, or socioeconomic status, violating fairness principles. |
| **Impacted Component** | `agents/explainability_agent.py`, `agents/responsible_ai_security_agent.py` |
| **Severity** | HIGH |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | Explainability system prompt explicitly forbids credibility judgements. Output gate scans for bias phrases (`_BIAS_PATTERNS`). Fairness tests use sensitive identity phrasings (race, gender, religion) and verify the system flags or filters them. |
| **Evidence** | `agents/explainability_agent.py` `_SYSTEM_PROMPT` fairness clause. `agents/responsible_ai_security_agent.py` `_BIAS_PATTERNS`. `tests/security/test_fairness_bias.py`. |

---

### R-09 — Model Version Drift / Reproducibility

| Field | Detail |
|-------|--------|
| **Risk** | A result produced today cannot be reproduced tomorrow because the underlying model was updated, making audit trails unreliable. |
| **Impacted Component** | `core/run_metadata.py`, `agents/orchestration_agent.py` |
| **Severity** | MEDIUM |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | `core/run_metadata.py` records model name, provider, prompt version constant, timestamp, transcript SHA-256 hash, and result summary for every run. Artifacts saved to `artifacts/runs/` with unique run IDs. Prompt version constants defined in each agent file. |
| **Evidence** | `core/run_metadata.py` — `save_run_metadata()`. `PROMPT_VERSION` constants in agent files. `artifacts/runs/` directory. |

---

### R-10 — Over-Blocking / Over-Filtering

| Field | Detail |
|-------|--------|
| **Risk** | Legitimate legal transcripts containing legally common terms (e.g., "override a judgment", "bypass the statute") are incorrectly blocked by the security agent, degrading system utility. |
| **Impacted Component** | `agents/responsible_ai_security_agent.py` |
| **Severity** | MEDIUM |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | Scoring threshold (0.5) requires multiple pattern hits, not a single keyword match. Single keyword hits score 0.25 — insufficient to block alone. `tests/security/test_prompt_injection.py` includes legitimate transcript samples verified NOT to be blocked. |
| **Evidence** | `agents/responsible_ai_security_agent.py` `injection_threshold = 0.5`. Legitimate transcript fixture in `tests/fixtures/clean_transcript.txt`. |

---

### R-11 — Unsafe Output Reaching End User

| Field | Detail |
|-------|--------|
| **Risk** | The final report contains language that could be misconstrued as a legal determination (e.g., "the defendant is guilty based on evidence"), causing harm if taken out of context. |
| **Impacted Component** | Output gate — `security_output_node` |
| **Severity** | HIGH |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | `_NEUTRALITY_VIOLATIONS` regex patterns scan the final report for 4 categories of prohibited conclusion language and redact them. All reports include a mandatory disclaimer. |
| **Evidence** | `agents/responsible_ai_security_agent.py` `_NEUTRALITY_VIOLATIONS` list. `agents/explainability_agent.py` `_build_clean_report()` — disclaimer footer. |

---

### R-12 — Insufficient Session Isolation

| Field | Detail |
|-------|--------|
| **Risk** | State from one user session leaks into another (e.g., cached LangGraph graph state, in-memory checkpointer) causing cross-contamination of analysis results. |
| **Impacted Component** | `core/memory.py`, `agents/orchestration_agent.py` |
| **Severity** | MEDIUM |
| **Likelihood** | LOW |
| **Residual Risk** | LOW |
| **Mitigation Strategy** | Each Streamlit session is assigned a unique UUID-based `thread_id` via `new_thread_id()`. LangGraph `InMemorySaver` uses `thread_id` as a key, ensuring complete isolation. Persistent memory store keys results by `run_id`. |
| **Evidence** | `core/memory.py` `new_thread_id()` — `uuid.uuid4()`. `agents/orchestration_agent.py` — `config["configurable"]["thread_id"] = tid`. |

---

## Risk Matrix

```
         │  LOW likelihood │ MEDIUM likelihood │ HIGH likelihood │
─────────┼─────────────────┼───────────────────┼─────────────────┤
HIGH sev │ R-03,R-05,R-07  │    R-01, R-02     │       —         │
         │ R-08,R-11        │                   │                 │
─────────┼─────────────────┼───────────────────┼─────────────────┤
MED sev  │ R-09,R-10,R-12  │    R-04, R-06     │       —         │
─────────┼─────────────────┼───────────────────┼─────────────────┤
LOW sev  │       —         │       —           │       —         │
```

---

*This register should be reviewed and updated at each sprint or whenever the model, prompts, or pipeline architecture change.*
