# TRUTHFORGE AI — Data Flow Diagram

```mermaid
sequenceDiagram
    actor User
    participant UI as Streamlit UI
    participant ORC as Orchestration Agent
    participant SEC_IN as Security Agent (Input)
    participant TP as Transcript Processing
    participant TR as Timeline Reconstruction
    participant CA as Consistency Analysis
    participant EX as Explainability
    participant SEC_OUT as Security Agent (Output)
    participant MEM as Memory Store
    participant META as Run Metadata
    participant LOG as Metrics / Logger

    User->>UI: Upload transcript PDF/TXT
    UI->>ORC: raw_transcript + llm_config
    ORC->>LOG: pipeline_start event (thread_id, chars)
    ORC->>META: open run record (run_id, model, timestamp, transcript_hash)

    ORC->>SEC_IN: raw_transcript
    SEC_IN->>SEC_IN: Regex injection patterns (18 patterns)
    SEC_IN->>SEC_IN: Role-confusion heuristics
    SEC_IN->>SEC_IN: Scoring (0.0–1.0)
    SEC_IN->>LOG: security_event (injection_detected / allowed)

    alt score >= 0.5 (BLOCKED)
        SEC_IN-->>ORC: security_input_blocked=True
        ORC-->>UI: Error state + security flags
        ORC->>LOG: pipeline_blocked (increment counter)
    else score < 0.5 (SAFE)
        SEC_IN-->>ORC: sanitized_transcript + flags
    end

    ORC->>TP: sanitized_transcript
    TP->>TP: spaCy NER (entities)
    TP->>TP: LLM → StructuredFactsModel
    Note over TP: Events, key_statements, summary
    TP-->>ORC: entities + structured_facts
    TP->>MEM: cache structured_facts (run_id)

    ORC->>TR: structured_facts
    TR->>TR: LLM → TimelineModel (sorted, ISO-8601)
    Note over TR: Normalised timestamps + confidence
    TR-->>ORC: timeline[]
    TR->>MEM: cache timeline snapshot (run_id)

    ORC->>CA: timeline + structured_facts + sanitized_transcript
    CA->>CA: LLM → ConsistencyReportModel
    Note over CA: Detects 6 inconsistency types

    alt Low confidence inconsistencies present
        CA-->>ORC: requires_review=True
        ORC->>CA: Second-pass analysis (re-invoke CA)
        CA-->>ORC: refined inconsistencies[]
    else
        CA-->>ORC: inconsistencies[]
    end

    ORC->>EX: inconsistencies + raw_transcript
    EX->>EX: LLM → ExplanationsModel
    Note over EX: Plain-English + evidence quotes + recommendations
    EX-->>ORC: explanations[] + final_report (draft)
    EX->>MEM: save run summary (run_id)

    ORC->>SEC_OUT: final_report (draft)
    SEC_OUT->>SEC_OUT: Neutrality violation scan
    SEC_OUT->>SEC_OUT: Bias pattern scan
    SEC_OUT->>LOG: security_event (output_filtered / clean)
    SEC_OUT-->>ORC: final_report (filtered) + output_flags

    ORC->>META: close run record (result_summary, duration_ms, inconsistency_count)
    ORC->>LOG: pipeline_complete (update avg_runtime, counters)

    ORC-->>UI: full TruthForgeState
    UI->>User: Tabbed results (Summary / Entities / Timeline / Inconsistencies / Explanations / Security / Audit / Report)
```

---

## State Object at Each Stage

```
START
  raw_transcript: "COURT HEARING..."

After SEC_IN:
+ sanitized_transcript: (cleaned)
+ security_input_flags: []
+ security_input_blocked: false
+ agent_statuses: {security_input: {status: "complete", confidence: "HIGH"}}

After TP:
+ entities: [{text, label, confidence, start, end}, ...]
+ structured_facts: {events: [...], key_statements: [...], summary: "..."}
+ agent_statuses: {..., transcript_processing: {status: "complete"}}

After TR:
+ timeline: [{event_id, description, timestamp, normalized_time, actors, location}, ...]
+ agent_statuses: {..., timeline_reconstruction: {status: "complete"}}

After CA:
+ inconsistencies: [{inconsistency_id, type, statement_a, statement_b, severity}, ...]
+ requires_review: false
+ agent_statuses: {..., consistency_analysis: {status: "complete", confidence: "HIGH"}}

After EX:
+ explanations: [{inconsistency_id, plain_english, evidence_quotes, confidence, recommendation}, ...]
+ final_report: "# TRUTHFORGE AI — Consistency Analysis Report..."
+ agent_statuses: {..., explainability: {status: "complete"}}

After SEC_OUT:
+ final_report: (filtered)
+ security_output_flags: []

END
+ audit_log: [14 entries across all agents]
+ error_state: null
```

---

## Data Persistence Map

| Data | Format | Location | Retention |
|------|--------|----------|-----------|
| Structured facts cache | JSON | `memory/{run_id}_facts.json` | Per-run |
| Timeline snapshot | JSON | `memory/{run_id}_timeline.json` | Per-run |
| Run summary | JSON | `memory/{run_id}_summary.json` | Persistent |
| Run metadata | JSON | `artifacts/runs/{run_id}.json` | Persistent |
| Pipeline events | JSONL | `logs/events.jsonl` | Append-only |
| Aggregate metrics | JSON | `logs/metrics.json` | Persistent |
| Security events | JSONL | `logs/events.jsonl` (tagged) | Append-only |
