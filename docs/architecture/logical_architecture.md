# TRUTHFORGE AI — Logical Architecture

```mermaid
graph TB
    subgraph UI["Streamlit Web UI"]
        UP[Upload / Demo Transcript]
        SB[Sidebar: Model Selector]
        RES[Results Tabs]
    end

    subgraph PIPELINE["LangGraph Multi-Agent Pipeline"]
        direction TB
        ORC[Orchestration Agent\nCoordinates pipeline flow]

        subgraph SECURITY_IN["Security Layer — Input Gate"]
            SI[Responsible AI Security Agent\nInjection Detection\nInput Sanitisation]
        end

        subgraph PROCESSING["Extraction & Structuring"]
            TP[Transcript Processing Agent\nspaCy NER + LLM Extraction\nEntities + Structured Facts]
            TR[Timeline Reconstruction Agent\nChronological Ordering\nNormalised Timestamps]
        end

        subgraph ANALYSIS["Analysis & Explanation"]
            CA[Consistency Analysis Agent\nInconsistency Detection\nSeverity Classification]
            EX[Explainability Agent\nPlain-English Explanations\nEvidence Quotes]
        end

        subgraph SECURITY_OUT["Security Layer — Output Gate"]
            SO[Responsible AI Security Agent\nNeutrality Filter\nPII Check]
        end
    end

    subgraph INFRA["Infrastructure & Observability"]
        LOG[Structured Logger\nlogs/events.jsonl]
        MET[Metrics Collector\nlogs/metrics.json]
        MEM[Memory Store\nmemory/ directory]
        META[Run Metadata\nartifacts/runs/]
    end

    subgraph LLM["LLM Providers"]
        ANT[Anthropic Claude]
        OAI[OpenAI GPT-4o]
        GGL[Google Gemini]
        OLL[Ollama Local]
        LMS[LM Studio Local]
    end

    UP --> ORC
    SB --> ORC
    ORC --> SI
    SI -->|blocked| RES
    SI -->|safe| TP
    TP --> TR
    TR --> CA
    CA --> EX
    EX --> SO
    SO --> RES

    TP & TR & CA & EX --> LLM
    ORC --> LOG
    ORC --> MET
    ORC --> META
    CA & EX --> MEM

    style SECURITY_IN fill:#ff9999,stroke:#cc0000
    style SECURITY_OUT fill:#ff9999,stroke:#cc0000
    style PROCESSING fill:#cce5ff,stroke:#0066cc
    style ANALYSIS fill:#d4edda,stroke:#28a745
    style INFRA fill:#fff3cd,stroke:#ffc107
    style LLM fill:#e2d9f3,stroke:#6f42c1
```

## Layer Descriptions

| Layer | Purpose |
|-------|---------|
| **Streamlit UI** | User-facing web interface; handles file upload, model selection, and tabbed results display |
| **Orchestration Agent** | LangGraph StateGraph coordinator; manages node sequencing, conditional edges, retry logic |
| **Security Input Gate** | First line of defence; blocks/flags adversarial transcripts before any LLM processes them |
| **Transcript Processing** | Converts raw text into entities (spaCy NER) and structured events (LLM structured output) |
| **Timeline Reconstruction** | Normalises timestamps and sorts events chronologically |
| **Consistency Analysis** | Detects logical inconsistencies, temporal conflicts, and evolving testimony |
| **Explainability** | Generates plain-English explanations with evidence quotes and recommendations |
| **Security Output Gate** | Final filter; removes neutrality violations and redacts unsafe conclusions |
| **Infrastructure** | Logging, metrics, memory, and run metadata — cross-cutting observability concerns |
| **LLM Providers** | Pluggable cloud and local model backends via LangChain `init_chat_model` |
