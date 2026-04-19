FROM python:3.11-slim

WORKDIR /app

# ── system deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps (cached layer) ────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── spaCy model (cached layer) ────────────────────────────────────────────────
RUN python -m spacy download en_core_web_sm

# ── app source ────────────────────────────────────────────────────────────────
COPY . .

# Create reports dir so the volume mount works cleanly
RUN mkdir -p /app/reports

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false", \
     "--global.developmentMode=false"]
