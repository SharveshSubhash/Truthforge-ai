"""
TRUTHFORGE AI — Streamlit Results Display
Renders pipeline output across tabbed sections.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd


def render_results(state: dict) -> None:
    """Render all pipeline results from the final TruthForgeState."""
    if not state:
        return

    error = state.get("error_state")
    if error:
        if "BLOCKED" in error:
            st.error(f"🛡️ **Security Alert:** {error}")
            _render_security_flags(
                state.get("security_input_flags", []),
                title="Input Security Flags",
            )
        else:
            st.error(f"❌ Pipeline Error: {error}")
        return

    tabs = st.tabs([
        "📋 Summary",
        "🔍 Entities",
        "📅 Timeline",
        "⚠️ Inconsistencies",
        "💡 Explanations",
        "🛡️ Security",
        "📊 Security Analytics",
        "📝 Audit Log",
        "📄 Full Report",
    ])

    with tabs[0]:
        _render_summary(state)
    with tabs[1]:
        _render_entities(state.get("entities", []))
    with tabs[2]:
        _render_timeline(state.get("timeline", []))
    with tabs[3]:
        _render_inconsistencies(state.get("inconsistencies", []))
    with tabs[4]:
        _render_explanations(state.get("explanations", []))
    with tabs[5]:
        _render_security_flags(state.get("security_input_flags", []), "Input Security Flags")
        _render_security_flags(state.get("security_output_flags", []), "Output Security Flags")
    with tabs[6]:
        _render_security_analytics()
    with tabs[7]:
        _render_audit_log(state.get("audit_log", []))
    with tabs[8]:
        _render_full_report(state.get("final_report", ""))


def _render_summary(state: dict) -> None:
    st.subheader("Analysis Summary")

    n_entities = len(state.get("entities", []))
    n_events = len(state.get("timeline", []))
    n_inconsistencies = len(state.get("inconsistencies", []))
    n_high = sum(1 for i in state.get("inconsistencies", []) if i.get("severity") == "HIGH")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Entities Extracted", n_entities)
    col2.metric("Timeline Events", n_events)
    col3.metric("Inconsistencies Found", n_inconsistencies,
                delta=f"{n_high} HIGH" if n_high else None,
                delta_color="inverse" if n_high else "off")
    col4.metric("Security Flags", len(state.get("security_input_flags", [])))

    if n_inconsistencies == 0:
        st.success("✅ No inconsistencies detected. The transcript appears internally consistent.")
    elif n_high > 0:
        st.error(f"🔴 {n_high} HIGH severity inconsistency/ies detected. Review required.")
    else:
        st.warning(f"🟡 {n_inconsistencies} minor inconsistency/ies detected.")

    # Structured facts summary
    sf = state.get("structured_facts", {})
    if sf.get("summary"):
        st.markdown("**Transcript Summary:**")
        st.info(sf["summary"])


def _render_entities(entities: list) -> None:
    st.subheader("Named Entities Extracted")
    if not entities:
        st.info("No entities extracted.")
        return

    df = pd.DataFrame(entities)
    # Keep only display columns
    cols = [c for c in ["text", "label", "confidence", "start", "end"] if c in df.columns]
    df = df[cols]
    if "confidence" in df.columns:
        df["confidence"] = df["confidence"].round(3)

    st.dataframe(
        df,
        column_config={
            "text":       st.column_config.TextColumn("Entity", width="medium"),
            "label":      st.column_config.TextColumn("Type", width="small"),
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1),
            "start":      st.column_config.NumberColumn("Start"),
            "end":        st.column_config.NumberColumn("End"),
        },
        hide_index=True,
        use_container_width=True,
    )

    # Entity type counts
    if "label" in df.columns:
        counts = df["label"].value_counts().reset_index()
        counts.columns = ["Type", "Count"]
        st.bar_chart(counts.set_index("Type"))


def _render_timeline(timeline: list) -> None:
    st.subheader("Reconstructed Timeline")
    if not timeline:
        st.info("No timeline events extracted.")
        return

    for ev in timeline:
        with st.expander(
            f"**{ev.get('event_id', '?')}** — {ev.get('description', '')[:80]}",
            expanded=False,
        ):
            col1, col2 = st.columns(2)
            col1.write(f"**Raw Timestamp:** {ev.get('timestamp') or 'Not specified'}")
            col2.write(f"**Normalised Time:** {ev.get('normalized_time') or 'Unknown'}")

            actors = ev.get("actors") or []
            if actors:
                st.write(f"**Actors:** {', '.join(actors)}")
            if ev.get("location"):
                st.write(f"**Location:** {ev['location']}")
            if ev.get("source_excerpt"):
                st.markdown(f'> "{ev["source_excerpt"]}"')


def _render_inconsistencies(inconsistencies: list) -> None:
    st.subheader("Detected Inconsistencies")
    if not inconsistencies:
        st.success("No inconsistencies detected.")
        return

    severity_colors = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}

    for inc in inconsistencies:
        sev = inc.get("severity", "MEDIUM")
        icon = severity_colors.get(sev, "⚪")
        with st.expander(
            f"{icon} **{inc.get('inconsistency_id', '?')}** — "
            f"{inc.get('type', 'UNKNOWN').replace('_', ' ')} [{sev}]",
            expanded=sev == "HIGH",
        ):
            st.markdown(f"**Type:** {inc.get('type', 'UNKNOWN')}")
            st.markdown(f"**Severity:** {sev}")
            st.markdown(f"**Explanation:** {inc.get('explanation', '')}")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Statement A:**")
                st.info(inc.get("statement_a", ""))
            with col2:
                st.markdown("**Statement B:**")
                st.info(inc.get("statement_b", ""))
            ids = []
            if inc.get("event_a_id"):
                ids.append(f"Event A: {inc['event_a_id']}")
            if inc.get("event_b_id"):
                ids.append(f"Event B: {inc['event_b_id']}")
            if ids:
                st.caption(" | ".join(ids))


def _render_explanations(explanations: list) -> None:
    st.subheader("Explanations for Legal Professionals")
    if not explanations:
        st.info("No explanations generated.")
        return

    for exp in explanations:
        iid = exp.get("inconsistency_id", "?")
        if iid == "NONE":
            st.success(exp.get("plain_english", "No issues found."))
            continue

        st.markdown(f"### {iid}")
        st.markdown(exp.get("plain_english", ""))

        quotes = exp.get("evidence_quotes", [])
        if quotes:
            st.markdown("**Evidence from transcript:**")
            for q in quotes:
                if q:
                    st.markdown(f'> "{q}"')

        col1, col2 = st.columns(2)
        col1.markdown(f"**Confidence:** {exp.get('confidence', 'MEDIUM')}")
        col2.markdown(f"**Recommended Action:** {exp.get('recommendation', '')}")
        st.divider()


def _render_security_flags(flags: list, title: str) -> None:
    st.subheader(title)
    if not flags:
        st.success("✅ No flags raised.")
        return
    for flag in flags:
        st.warning(f"🚩 {flag}")


def _render_security_analytics() -> None:
    """Render the Security Analytics panel showing runtime security telemetry."""
    st.subheader("Security Analytics — Runtime Telemetry")
    st.caption("Live counters from logs/metrics.json — updated after every pipeline run.")

    try:
        from core.metrics import metrics as _metrics
        snap = _metrics.get_snapshot()

        # --- Aggregate counters ---
        total_runs = snap.get("pipeline_runs_total", 0)
        blocked = snap.get("pipeline_blocked_total", 0)
        failures = snap.get("pipeline_failures_total", 0)
        second_pass = snap.get("pipeline_second_pass_total", 0)
        avg_rt = snap.get("avg_runtime_ms", 0.0)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Pipeline Runs", total_runs)
        col2.metric("Inputs Blocked", blocked,
                    delta="attack" if blocked > 0 else None,
                    delta_color="inverse" if blocked > 0 else "off")
        col3.metric("Pipeline Failures", failures,
                    delta="error" if failures > 0 else None,
                    delta_color="inverse" if failures > 0 else "off")
        col4.metric("Avg Runtime (ms)", f"{avg_rt:.0f}")

        st.divider()

        # --- Security event breakdown ---
        st.markdown("**Security Event Counts by Category**")
        sec_events = snap.get("security_event_counts", {})
        if sec_events:
            event_labels = {
                "injection_detected":       "Injections Blocked",
                "suspicious_input_allowed": "Suspicious (Allowed with Warning)",
                "output_filtered":          "Outputs Filtered",
                "bias_detected":            "Bias / Identity Language Detected",
                "neutrality_violation":     "Neutrality Violations",
                "clean_input":              "Clean Inputs",
                "clean_output":             "Clean Outputs",
            }
            rows = [
                {"Event": event_labels.get(k, k), "Count": v}
                for k, v in sec_events.items()
            ]
            df = pd.DataFrame(rows).sort_values("Count", ascending=False)
            st.dataframe(df, hide_index=True, use_container_width=True)

            # Bar chart of attack/filter events (exclude clean_* for clarity)
            attack_rows = [r for r in rows if not r["Event"].startswith("Clean")]
            if attack_rows:
                chart_df = pd.DataFrame(attack_rows).set_index("Event")
                st.bar_chart(chart_df)
        else:
            st.info("No security events recorded yet. Run the pipeline to see telemetry.")

        st.divider()

        # --- Second-pass autonomy counter ---
        if second_pass > 0:
            st.info(f"**Autonomy second-pass re-analyses triggered:** {second_pass}")

        # --- Recent runtime trend ---
        recent = snap.get("recent_runtimes_ms_preview", snap.get("recent_runtimes_ms", []))
        if len(recent) > 1:
            st.markdown("**Recent Pipeline Runtimes (ms)**")
            rt_df = pd.DataFrame({"Run": range(1, len(recent)+1), "Runtime (ms)": recent})
            st.line_chart(rt_df.set_index("Run"))

    except Exception as e:
        st.warning(f"Security analytics unavailable: {e}")


def _render_audit_log(audit_log: list) -> None:
    st.subheader("Full Audit Log")
    if not audit_log:
        st.info("No audit entries recorded.")
        return
    st.caption(f"{len(audit_log)} entries")
    log_text = "\n".join(audit_log)
    st.text_area("Audit Log", log_text, height=400, disabled=True)


def _render_full_report(report: str) -> None:
    st.subheader("Full Analysis Report")
    if not report:
        st.info("No report generated.")
        return
    st.markdown(report)
    st.download_button(
        label="📥 Download Report (Markdown)",
        data=report,
        file_name="truthforge_report.md",
        mime="text/markdown",
    )
