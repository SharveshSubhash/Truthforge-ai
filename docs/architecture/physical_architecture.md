# TRUTHFORGE AI — Physical / Deployment Architecture

```mermaid
graph TB
    subgraph HOST["Host Machine (macOS / Windows)"]
        subgraph DOCKER["Docker Engine"]
            subgraph CONTAINER["truthforge-ai container\n(python:3.11-slim)"]
                direction TB
                APP["Streamlit App\nmain.py\nPort 8501"]
                AGENTS["Agent Modules\n/agents/"]
                CORE["Core Modules\n/core/"]
                UI["UI Modules\n/ui/"]
            end
        end

        subgraph VOLUMES["Host-Mounted Volumes"]
            ENV[".env\nAPI keys"]
            LOGS["logs/\nevents.jsonl\nmetrics.json"]
            ARTIFACTS["artifacts/\nruns/*.json"]
            MEMORY["memory/\nfacts, snapshots"]
        end

        subgraph LOCAL_MODELS["Local Model Servers (optional)"]
            OLLAMA["Ollama\nlocalhost:11434"]
            LMSTUDIO["LM Studio\nlocalhost:1234"]
        end
    end

    subgraph CLOUD["Cloud / External Services"]
        ANTHROPIC["Anthropic API\napi.anthropic.com"]
        OPENAI["OpenAI API\napi.openai.com"]
        GOOGLE["Google AI API\ngenerativelanguage.googleapis.com"]
    end

    subgraph USER["User"]
        BROWSER["Web Browser\nlocalhost:8501"]
    end

    BROWSER -->|HTTP| APP
    APP --> AGENTS
    APP --> CORE
    APP --> UI
    AGENTS --> CORE

    CONTAINER -.->|read| ENV
    CORE -.->|write| LOGS
    CORE -.->|write| ARTIFACTS
    CORE -.->|read/write| MEMORY

    AGENTS -->|HTTPS API calls| ANTHROPIC
    AGENTS -->|HTTPS API calls| OPENAI
    AGENTS -->|HTTPS API calls| GOOGLE
    AGENTS -->|HTTP localhost| OLLAMA
    AGENTS -->|HTTP localhost| LMSTUDIO

    style CONTAINER fill:#cce5ff,stroke:#0066cc
    style VOLUMES fill:#fff3cd,stroke:#ffc107
    style CLOUD fill:#e2d9f3,stroke:#6f42c1
    style LOCAL_MODELS fill:#d4edda,stroke:#28a745
```

## Deployment Configurations

### Development (macOS)
```bash
# Direct Python
streamlit run main.py

# Or Docker
docker compose up --build
```

### Production (Docker)
```yaml
# docker-compose.yml
services:
  truthforge:
    build: .
    ports: ["8501:8501"]
    volumes:
      - ./.env:/app/.env:ro
      - ./logs:/app/logs
      - ./artifacts:/app/artifacts
      - ./memory:/app/memory
    environment:
      - PYTHONUNBUFFERED=1
```

### Windows Distribution
```
TRUTHFORGE_AI_Windows.zip
├── 1_SETUP.bat      → docker build
├── 2_START.bat      → docker compose up
├── 3_STOP.bat       → docker compose down
└── .env.example     → user fills in API keys
```

## Port and Network Map

| Service | Port | Protocol | Direction |
|---------|------|----------|-----------|
| Streamlit UI | 8501 | HTTP | Inbound (browser → container) |
| Anthropic API | 443 | HTTPS | Outbound (container → cloud) |
| OpenAI API | 443 | HTTPS | Outbound (container → cloud) |
| Google API | 443 | HTTPS | Outbound (container → cloud) |
| Ollama | 11434 | HTTP | Outbound (container → host) |
| LM Studio | 1234 | HTTP | Outbound (container → host) |

## Resource Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 2 GB | 4 GB |
| CPU | 2 cores | 4 cores |
| Disk | 5 GB (Docker image) | 10 GB |
| Network | Required for cloud LLMs | — |
