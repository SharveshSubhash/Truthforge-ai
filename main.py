"""
TRUTHFORGE AI — Streamlit Application Entry Point
================================================================
Run with: streamlit run main.py
"""

from __future__ import annotations
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="TRUTHFORGE AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.sidebar import render_sidebar
from ui.upload import render_upload
from ui.results import render_results
from ui.monitoring import render_monitoring


def _inject_css(sidebar_width_px: int):
    css = """
<style>
/* ── Typography ─────────────────────────────────────────────── */
h1 { font-size: 1.6rem !important; font-weight: 700 !important; letter-spacing: -0.5px; }
h2 { font-size: 1.15rem !important; font-weight: 600 !important; }
h3 { font-size: 1rem !important; font-weight: 600 !important; }

/* ── Tabs — slim underline style ────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #2c2c2c; }
.stTabs [data-baseweb="tab"] {
    font-size: 0.78rem; font-weight: 500;
    padding: 6px 14px; color: #aaa;
    border-radius: 4px 4px 0 0;
}
.stTabs [aria-selected="true"] {
    color: #4da6ff !important;
    border-bottom: 2px solid #4da6ff !important;
    background: transparent !important;
}

/* ── Metric cards ───────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #1a1a2e; border: 1px solid #2a2a3e;
    border-radius: 6px; padding: 12px 16px !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important; color: #888 !important;
    text-transform: uppercase; letter-spacing: 0.5px;
}
[data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700 !important; }

/* ── Sidebar ─────────────────────────────────────────────────── */
[data-testid="stSidebar"] { border-right: 1px solid #2a2a2a; }
[data-testid="stSidebar"] {
    min-width: __SIDEBAR_WIDTH__px !important;
    max-width: __SIDEBAR_WIDTH__px !important;
}
[data-testid="stSidebar"] > div:first-child {
    min-width: __SIDEBAR_WIDTH__px !important;
    max-width: __SIDEBAR_WIDTH__px !important;
}
[data-testid="stSidebar"] .stRadio label { font-size: 0.85rem; }

/* ── Dataframes ─────────────────────────────────────────────── */
[data-testid="stDataFrame"] { border-radius: 6px; overflow: hidden; }

/* ── Section label ──────────────────────────────────────────── */
.section-label {
    font-size: 0.68rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
    color: #4da6ff; margin-bottom: 8px;
}

/* ── Finding card ───────────────────────────────────────────── */
.finding-card {
    background: #1a1a2e; border-left: 3px solid #4da6ff;
    border-radius: 0 6px 6px 0; padding: 14px 18px; margin-bottom: 12px;
}
.finding-card.high   { border-left-color: #c0392b; }
.finding-card.medium { border-left-color: #e67e22; }
.finding-card.low    { border-left-color: #27ae60; }

/* ── Evidence quote ─────────────────────────────────────────── */
.evidence-quote {
    background: #12121f; border-left: 3px solid #555;
    border-radius: 0 4px 4px 0; padding: 10px 14px;
    font-size: 0.85rem; color: #ccc; font-style: italic; margin: 6px 0;
}

/* ── Badges ─────────────────────────────────────────────────── */
.badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 0.7rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
}
.badge-high   { background: #c0392b22; color: #e74c3c; border: 1px solid #c0392b; }
.badge-medium { background: #e67e2222; color: #e67e22; border: 1px solid #e67e22; }
.badge-low    { background: #27ae6022; color: #27ae60; border: 1px solid #27ae60; }
.badge-clean  { background: #27ae6022; color: #27ae60; border: 1px solid #27ae60; }

/* ── Step list ──────────────────────────────────────────────── */
.step-item {
    padding: 6px 12px; border-left: 2px solid #4da6ff;
    margin: 4px 0; font-size: 0.85rem; color: #ccc;
}
</style>
"""
    st.markdown(css.replace("__SIDEBAR_WIDTH__", str(sidebar_width_px)), unsafe_allow_html=True)


def _init_session():
    defaults = {
        "pipeline_result": None,
        "pipeline_ran":    False,
        "thread_id":       None,
        "has_uploaded":    False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main():
    _init_session()
    sidebar_width_px = 320
    _inject_css(sidebar_width_px)

    with st.sidebar:
        st.markdown(
            '<div style="padding:8px 0 4px">'
            '<span style="font-size:1.1rem;font-weight:700">⚖️ TRUTHFORGE AI</span><br>'
            '<span style="font-size:0.75rem;color:#888">Legal Transcript Analyser</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        # --- Model config — collapsed by default ---
        st.markdown('<p class="section-label">Controls</p>', unsafe_allow_html=True)
        with st.expander("⚙️ Model Settings", expanded=False):
            llm_config = render_sidebar()

        st.divider()

        # --- Monitoring — demoted to bottom ---
        st.markdown(
            '<span style="font-size:0.72rem;color:#666;text-transform:uppercase;'
            'letter-spacing:0.5px">System</span>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("show_monitoring"):
            if st.button("← Back to Analysis", use_container_width=True):
                st.session_state["show_monitoring"] = False
                st.rerun()
        else:
            show_monitoring = st.button("📊 Open Monitoring Dashboard", use_container_width=True)
            if show_monitoring:
                st.session_state["show_monitoring"] = True
                st.rerun()

    # --- Monitoring page ---
    if st.session_state.get("show_monitoring"):
        render_monitoring()
        return

    # --- Main header ---
    st.markdown(
        '<h1>⚖️ TRUTHFORGE AI</h1>'
        '<p style="color:#888;font-size:0.9rem;margin-top:-8px">'
        'Multi-agent legal transcript consistency analyser · '
        'Upload a transcript to detect contradictions, reconstruct timelines, '
        'and generate court-ready explanations.'
        '</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    # --- Main workspace upload area ---
    transcript_text = render_upload()

    # --- Onboarding hint ---
    if not st.session_state.has_uploaded and transcript_text is None:
        st.info(
            "**Getting started:** Upload a legal transcript PDF, TXT, or DOCX above, "
            "then click **Analyse Transcript** to run the pipeline."
        )

    if transcript_text:
        st.session_state.has_uploaded = True

    # --- Run button + status ---
    col_btn, col_status = st.columns([2, 5])
    with col_btn:
        run_clicked = st.button(
            "🔍 Analyse Transcript",
            type="primary",
            disabled=(transcript_text is None),
            use_container_width=True,
        )
    with col_status:
        if transcript_text is None:
            st.markdown(
                '<p style="color:#666;font-size:0.85rem;margin-top:8px">'
                'Upload a transcript file above to begin.</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<p style="color:#27ae60;font-size:0.85rem;margin-top:8px">'
                f'✓ Transcript ready ({len(transcript_text):,} characters). '
                f'Click <strong>Analyse Transcript</strong> to run.</p>',
                unsafe_allow_html=True,
            )

    # --- Pipeline execution ---
    if run_clicked and transcript_text:
        st.divider()
        _run_pipeline(transcript_text, llm_config)

    # --- Completion banner + results ---
    if st.session_state.pipeline_ran and st.session_state.pipeline_result:
        state = st.session_state.pipeline_result
        n_inc = len(state.get("inconsistencies", []))
        report = state.get("final_report", "")

        st.divider()

        # Completion banner
        if state.get("error_state"):
            pass  # error already shown in render_results
        elif n_inc == 0:
            st.success("✅ **Analysis complete** — No inconsistencies detected.")
        else:
            n_high = sum(1 for i in state.get("inconsistencies", []) if i.get("severity") == "HIGH")
            col_banner, col_dl = st.columns([3, 1])
            with col_banner:
                if n_high:
                    st.error(f"⚠️ **Analysis complete** — {n_inc} inconsistency/ies found ({n_high} HIGH severity).")
                else:
                    st.warning(f"⚠️ **Analysis complete** — {n_inc} inconsistency/ies found.")
            with col_dl:
                if report:
                    st.download_button(
                        "📥 Download Report",
                        data=report,
                        file_name="truthforge_report.md",
                        mime="text/markdown",
                        type="primary",
                        use_container_width=True,
                    )

        render_results(state)


def _run_pipeline(transcript: str, llm_config: dict):
    from agents.orchestration_agent import stream_pipeline
    from core.memory import new_thread_id

    thread_id = new_thread_id()
    st.session_state.thread_id = thread_id
    accumulated: dict = {"audit_log": []}

    steps = [
        ("security_input",          "Validating input for security threats..."),
        ("transcript_processing",   "Extracting named entities and events..."),
        ("timeline_reconstruction", "Reconstructing chronological timeline..."),
        ("consistency_analysis",    "Checking for contradictions and inconsistencies..."),
        ("explainability",          "Generating plain-English explanations..."),
        ("security_output",         "Filtering output for security compliance..."),
        ("error",                   "Error encountered"),
    ]
    step_labels = dict(steps)

    with st.status("Running analysis pipeline...", expanded=True) as status:
        try:
            for node_name, state_update in stream_pipeline(
                transcript,
                llm_config=llm_config,
                thread_id=thread_id,
            ):
                label = step_labels.get(node_name, f"Running {node_name}...")
                st.write(label)

                for k, v in state_update.items():
                    if k == "audit_log" and isinstance(v, list):
                        accumulated["audit_log"].extend(v)
                    else:
                        accumulated[k] = v

                if state_update.get("security_input_blocked"):
                    st.warning("⛔ Input blocked by security agent.")
                    break

            status.update(label="✅ Analysis complete!", state="complete", expanded=False)
            st.session_state.pipeline_result = accumulated
            st.session_state.pipeline_ran = True

        except Exception as exc:
            status.update(label=f"❌ Pipeline failed: {exc}", state="error")
            st.error(f"Pipeline error: {exc}")
            accumulated["error_state"] = str(exc)
            st.session_state.pipeline_result = accumulated
            st.session_state.pipeline_ran = True


if __name__ == "__main__":
    main()
