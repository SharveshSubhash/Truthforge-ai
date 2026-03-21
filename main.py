"""
TRUTHFORGE AI — Streamlit Application Entry Point
================================================================
Run with: streamlit run main.py

Features
--------
• Model selector sidebar (cloud: Claude, GPT-4o, Gemini | local: Ollama, LM Studio)
• File upload (TXT, PDF, DOCX)
• Live pipeline progress using st.status
• Tabbed results: entities, timeline, inconsistencies, explanations, security, audit log
• Download final report as Markdown
"""

from __future__ import annotations
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Page config must be called first
st.set_page_config(
    page_title="TRUTHFORGE AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.sidebar import render_sidebar
from ui.upload import render_upload
from ui.results import render_results

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

def _init_session():
    defaults = {
        "pipeline_result": None,
        "pipeline_ran": False,
        "thread_id": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main():
    _init_session()

    # Sidebar — returns LangGraph config
    llm_config = render_sidebar()

    # Header
    st.title("⚖️ TRUTHFORGE AI")
    st.markdown(
        "**Forging Truth from Legal Testimony Using Multi-Agent AI** | "
        "Analyse legal transcripts for factual inconsistencies."
    )
    st.divider()

    # Upload section
    transcript_text = render_upload()

    st.divider()

    # Run button
    col1, col2 = st.columns([1, 4])
    with col1:
        run_clicked = st.button(
            "🔍 Analyse Transcript",
            type="primary",
            disabled=(transcript_text is None),
            use_container_width=True,
        )
    with col2:
        if transcript_text is None:
            st.info("Upload a transcript file or enable the demo transcript to begin.")
        else:
            st.success(f"Transcript ready ({len(transcript_text):,} characters). Click **Analyse Transcript** to run.")

    # --- Pipeline execution ---
    if run_clicked and transcript_text:
        st.divider()
        _run_pipeline(transcript_text, llm_config)

    # --- Display results ---
    if st.session_state.pipeline_ran and st.session_state.pipeline_result:
        st.divider()
        render_results(st.session_state.pipeline_result)


def _run_pipeline(transcript: str, llm_config: dict):
    """Execute the pipeline with live progress display."""
    from agents.orchestration_agent import stream_pipeline
    from core.memory import new_thread_id

    thread_id = new_thread_id()
    st.session_state.thread_id = thread_id

    # Accumulated state (stream updates are partial)
    accumulated: dict = {"audit_log": []}

    step_labels = {
        "security_input":           "🛡️ Security Input Gate — checking for adversarial inputs...",
        "transcript_processing":    "🔍 Transcript Processing — extracting entities and events...",
        "timeline_reconstruction":  "📅 Timeline Reconstruction — ordering events chronologically...",
        "consistency_analysis":     "⚠️ Consistency Analysis — detecting contradictions...",
        "explainability":           "💡 Explainability — generating human-readable explanations...",
        "security_output":          "🛡️ Security Output Gate — filtering final report...",
        "error":                    "❌ Error occurred",
    }

    with st.status("Running TRUTHFORGE AI pipeline...", expanded=True) as status:
        try:
            for node_name, state_update in stream_pipeline(
                transcript,
                llm_config=llm_config,
                thread_id=thread_id,
            ):
                label = step_labels.get(node_name, f"Running {node_name}...")
                st.write(label)

                # Merge update into accumulated state
                for k, v in state_update.items():
                    if k == "audit_log" and isinstance(v, list):
                        accumulated["audit_log"].extend(v)
                    else:
                        accumulated[k] = v

                # Show early warning if blocked
                if state_update.get("security_input_blocked"):
                    st.warning("⛔ Input blocked by security agent. Pipeline halted.")
                    break

            status.update(label="✅ Analysis complete!", state="complete", expanded=False)
            st.session_state.pipeline_result = accumulated
            st.session_state.pipeline_ran = True

        except Exception as exc:
            status.update(label=f"❌ Error: {exc}", state="error")
            st.error(f"Pipeline failed: {exc}")
            accumulated["error_state"] = str(exc)
            st.session_state.pipeline_result = accumulated
            st.session_state.pipeline_ran = True


if __name__ == "__main__":
    main()
