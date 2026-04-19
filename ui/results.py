"""
TRUTHFORGE AI — Streamlit Results Display
Renders pipeline output across tabbed sections.
"""

from __future__ import annotations
import json
from pathlib import Path

import streamlit as st
import pandas as pd

_EVAL_METRICS_PATH = Path(__file__).parent.parent / "logs" / "eval_metrics.json"


def _render_horizontal_bar_chart(
    df: pd.DataFrame,
    label_col: str,
    value_col: str,
    *,
    color: str = "#7db7e8",
    min_height: int = 220,
    label_limit: int = 420,
) -> None:
    """Render a horizontal bar chart with readable labels."""
    try:
        import altair as alt

        chart_df = df[[label_col, value_col]].copy().sort_values(value_col, ascending=False)
        chart = (
            alt.Chart(chart_df)
            .mark_bar(color=color, cornerRadiusEnd=3)
            .encode(
                x=alt.X(f"{value_col}:Q", title=value_col),
                y=alt.Y(
                    f"{label_col}:N",
                    sort="-x",
                    title=None,
                    axis=alt.Axis(labelLimit=label_limit, labelPadding=10),
                ),
                tooltip=[
                    alt.Tooltip(f"{label_col}:N", title=label_col),
                    alt.Tooltip(f"{value_col}:Q", title=value_col),
                ],
            )
            .properties(height=max(min_height, len(chart_df) * 44))
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.dataframe(df[[label_col, value_col]], hide_index=True, use_container_width=True)


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
        "📋 Results",
        "⚠️ Inconsistencies",
        "📅 Timeline",
        "📄 Full Report",
        "🔍 Entities",
        "🔧 Diagnostics",
    ])

    with tabs[0]:
        _render_summary(state)
    with tabs[1]:
        # Inconsistencies + Explanations merged
        _render_inconsistencies(state.get("inconsistencies", []))
        st.divider()
        st.markdown('<p class="section-label">AI-Generated Explanations</p>',
                    unsafe_allow_html=True)
        _render_explanations(state.get("explanations", []))
    with tabs[2]:
        _render_timeline(state.get("timeline", []))
    with tabs[3]:
        _render_full_report(state.get("final_report", ""))
    with tabs[4]:
        _render_entities(state.get("entities", []))
    with tabs[5]:
        diag = st.tabs(["🛡️ Security Flags", "📊 Security Analytics", "🎯 Eval Metrics", "📝 Audit Log"])
        with diag[0]:
            _render_security_flags(state.get("security_input_flags", []), "Input Security Flags")
            _render_security_flags(state.get("security_output_flags", []), "Output Security Flags")
        with diag[1]:
            _render_security_analytics(state)
        with diag[2]:
            _render_eval_metrics(state)
        with diag[3]:
            _render_audit_log(state.get("audit_log", []))


def _render_summary(state: dict) -> None:
    n_entities       = len(state.get("entities", []))
    n_events         = len(state.get("timeline", []))
    n_inconsistencies = len(state.get("inconsistencies", []))
    n_high   = sum(1 for i in state.get("inconsistencies", []) if i.get("severity") == "HIGH")
    n_medium = sum(1 for i in state.get("inconsistencies", []) if i.get("severity") == "MEDIUM")
    n_low    = sum(1 for i in state.get("inconsistencies", []) if i.get("severity") == "LOW")
    n_sec    = len(state.get("security_input_flags", []))

    # --- Risk banner ---
    if n_inconsistencies == 0:
        st.markdown(
            '<div style="background:#0d3b0d;border-left:4px solid #27ae60;padding:14px 20px;'
            'border-radius:0 6px 6px 0;margin-bottom:16px">'
            '<span style="font-size:1rem;font-weight:700;color:#27ae60">✅ TRANSCRIPT CLEAR</span>'
            '<span style="color:#aaa;font-size:0.85rem;margin-left:12px">'
            'No inconsistencies detected. Transcript appears internally consistent.</span></div>',
            unsafe_allow_html=True,
        )
    elif n_high > 0:
        st.markdown(
            f'<div style="background:#3b0d0d;border-left:4px solid #c0392b;padding:14px 20px;'
            f'border-radius:0 6px 6px 0;margin-bottom:16px">'
            f'<span style="font-size:1rem;font-weight:700;color:#e74c3c">⚠ HIGH RISK — REVIEW REQUIRED</span>'
            f'<span style="color:#aaa;font-size:0.85rem;margin-left:12px">'
            f'{n_high} high-severity finding(s) require immediate attention.</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:#3b2a0d;border-left:4px solid #e67e22;padding:14px 20px;'
            f'border-radius:0 6px 6px 0;margin-bottom:16px">'
            f'<span style="font-size:1rem;font-weight:700;color:#e67e22">⚠ FINDINGS DETECTED</span>'
            f'<span style="color:#aaa;font-size:0.85rem;margin-left:12px">'
            f'{n_inconsistencies} inconsistency/ies flagged for review.</span></div>',
            unsafe_allow_html=True,
        )

    # --- KPI row ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entities Extracted", n_entities)
    c2.metric("Timeline Events", n_events)
    c3.metric("Inconsistencies", n_inconsistencies,
              delta=f"{n_high} HIGH" if n_high else None,
              delta_color="inverse" if n_high else "off")
    c4.metric("Security Flags", n_sec,
              delta="flagged" if n_sec else None,
              delta_color="inverse" if n_sec else "off")

    # --- Severity matrix (only if findings exist) ---
    if n_inconsistencies > 0:
        st.markdown('<p class="section-label" style="margin-top:20px">Severity Breakdown</p>',
                    unsafe_allow_html=True)
        s1, s2, s3 = st.columns(3)
        s1.metric("🔴 High", n_high)
        s2.metric("🟡 Medium", n_medium)
        s3.metric("🟢 Low", n_low)

    # --- Transcript summary ---
    sf = state.get("structured_facts", {})
    if sf.get("summary"):
        st.markdown('<p class="section-label" style="margin-top:20px">Transcript Summary</p>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div style="background:#12121f;border-radius:6px;padding:14px 18px;'
            f'color:#ccc;font-size:0.9rem;line-height:1.6">{sf["summary"]}</div>',
            unsafe_allow_html=True,
        )


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
        _render_horizontal_bar_chart(counts, "Type", "Count", min_height=180, label_limit=220)


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
    if not inconsistencies:
        st.markdown(
            '<div style="background:#0d3b0d;border-left:4px solid #27ae60;padding:14px 20px;'
            'border-radius:0 6px 6px 0">'
            '<span style="color:#27ae60;font-weight:700">✅ No inconsistencies detected.</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # --- Summary table (sortable overview) ---
    st.markdown('<p class="section-label">Overview</p>', unsafe_allow_html=True)
    badge_map = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
    rows = []
    for inc in inconsistencies:
        sev = inc.get("severity", "MEDIUM")
        rows.append({
            "ID":       inc.get("inconsistency_id", "—"),
            "Type":     inc.get("type", "UNKNOWN").replace("_", " ").title(),
            "Severity": sev,
            "Summary":  inc.get("explanation", "")[:90] + ("…" if len(inc.get("explanation", "")) > 90 else ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "ID":       st.column_config.TextColumn("ID", width="small"),
            "Type":     st.column_config.TextColumn("Type", width="medium"),
            "Severity": st.column_config.TextColumn("Severity", width="small"),
            "Summary":  st.column_config.TextColumn("Finding", width="large"),
        },
        hide_index=True,
        use_container_width=True,
    )

    st.markdown('<p class="section-label" style="margin-top:20px">Detail</p>',
                unsafe_allow_html=True)

    for inc in inconsistencies:
        sev      = inc.get("severity", "MEDIUM").upper()
        sev_cls  = badge_map.get(sev, "medium")
        inc_id   = inc.get("inconsistency_id", "?")
        inc_type = inc.get("type", "UNKNOWN").replace("_", " ").title()

        badge_html = f'<span class="badge badge-{sev_cls}">{sev}</span>'
        st.markdown(
            f'<div class="finding-card {sev_cls}">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
            f'<span style="font-weight:700;font-size:0.95rem">{inc_id}</span>'
            f'{badge_html}'
            f'<span style="color:#888;font-size:0.8rem">{inc_type}</span>'
            f'</div>'
            f'<p style="color:#ddd;font-size:0.88rem;margin:0">{inc.get("explanation", "")}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<p style="font-size:0.75rem;color:#888;margin-bottom:4px">STATEMENT A</p>',
                        unsafe_allow_html=True)
            st.info(inc.get("statement_a", "—"))
        with col2:
            st.markdown('<p style="font-size:0.75rem;color:#888;margin-bottom:4px">STATEMENT B</p>',
                        unsafe_allow_html=True)
            st.info(inc.get("statement_b", "—"))

        ids = []
        if inc.get("event_a_id"):
            ids.append(f"Event A: {inc['event_a_id']}")
        if inc.get("event_b_id"):
            ids.append(f"Event B: {inc['event_b_id']}")
        if ids:
            st.caption(" | ".join(ids))
        st.markdown("<hr style='border:none;border-top:1px solid #2a2a2a;margin:12px 0'>",
                    unsafe_allow_html=True)


def _render_explanations(explanations: list) -> None:
    st.markdown('<p class="section-label">Findings for Legal Professionals</p>',
                unsafe_allow_html=True)
    if not explanations:
        st.info("No explanations generated.")
        return

    conf_cls = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}

    for exp in explanations:
        iid = exp.get("inconsistency_id", "?")
        if iid in ("NONE", "NO_ISSUES"):
            st.markdown(
                '<div style="background:#0d3b0d;border-left:4px solid #27ae60;'
                'padding:14px 20px;border-radius:0 6px 6px 0">'
                f'<span style="color:#27ae60;font-weight:700">✅ {exp.get("plain_english", "No issues found.")}</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            continue

        conf     = exp.get("confidence", "MEDIUM").upper()
        cls      = conf_cls.get(conf, "medium")
        quotes   = [q for q in exp.get("evidence_quotes", []) if q]
        rec      = exp.get("recommendation", "")
        plain    = exp.get("plain_english", "")

        left, right = st.columns([3, 2])

        with left:
            st.markdown(
                f'<div class="finding-card {cls}">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
                f'<span style="font-weight:700">{iid}</span>'
                f'<span class="badge badge-{cls}">{conf} CONFIDENCE</span>'
                f'</div>'
                f'<p style="color:#ddd;font-size:0.9rem;line-height:1.6;margin:0">{plain}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if rec:
                st.markdown(
                    f'<div style="background:#1a1a2e;border:1px solid #2a2a3e;border-radius:6px;'
                    f'padding:10px 14px;margin-top:8px">'
                    f'<span style="font-size:0.7rem;color:#4da6ff;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.5px">Recommended Action</span>'
                    f'<p style="color:#ccc;font-size:0.87rem;margin:4px 0 0">{rec}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        with right:
            if quotes:
                st.markdown(
                    '<p style="font-size:0.7rem;color:#4da6ff;font-weight:600;'
                    'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">'
                    'Evidence from Transcript</p>',
                    unsafe_allow_html=True,
                )
                for q in quotes:
                    st.markdown(
                        f'<div class="evidence-quote">"{q}"</div>',
                        unsafe_allow_html=True,
                    )

        st.markdown("<hr style='border:none;border-top:1px solid #2a2a2a;margin:16px 0'>",
                    unsafe_allow_html=True)


def _render_security_flags(flags: list, title: str) -> None:
    st.subheader(title)
    if not flags:
        st.success("✅ No flags raised.")
        return
    for flag in flags:
        st.warning(f"🚩 {flag}")


def _render_security_analytics(state: dict) -> None:
    """Render the Security Analytics panel showing runtime security telemetry."""
    st.subheader("Security Analytics — Runtime Telemetry")
    tab_run, tab_cum = st.tabs(["Analysed Transcript", "Cumulative"])

    with tab_run:
        _render_security_analytics_run(state)

    with tab_cum:
        _render_security_analytics_cumulative()


def _render_security_analytics_run(state: dict) -> None:
    """Render security analytics for the currently analysed transcript only."""
    st.caption("Security outcome for the currently analysed transcript.")

    input_flags = state.get("security_input_flags", []) or []
    output_flags = state.get("security_output_flags", []) or []
    blocked = bool(state.get("security_input_blocked"))
    final_report = state.get("final_report", "") or ""
    pii_redacted = "[REDACTED:" in final_report

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Input Flags", len(input_flags))
    c2.metric("Output Flags", len(output_flags))
    c3.metric("Blocked", "Yes" if blocked else "No")
    c4.metric("PII Redacted", "Yes" if pii_redacted else "No")

    status_lines = []
    if blocked:
        status_lines.append("Input security gate blocked this transcript before analysis.")
    else:
        status_lines.append("Transcript passed the input security gate and completed analysis.")
    if output_flags:
        status_lines.append(f"Output review raised {len(output_flags)} flag(s).")
    else:
        status_lines.append("Output review did not raise any flags.")
    st.info(" ".join(status_lines))

    col_in, col_out = st.columns(2)
    with col_in:
        st.markdown("**Input Flag Details**")
        if input_flags:
            for flag in input_flags:
                st.warning(f"🚩 {flag}")
        else:
            st.success("✅ No input security flags for this transcript.")
    with col_out:
        st.markdown("**Output Flag Details**")
        if output_flags:
            for flag in output_flags:
                st.warning(f"🚩 {flag}")
        else:
            st.success("✅ No output security flags for this transcript.")


def _render_security_analytics_cumulative() -> None:
    """Render cumulative runtime security telemetry."""
    st.caption("Live counters from logs/metrics.json — updated after every pipeline run.")

    try:
        from core.metrics import metrics as _metrics
        snap = _metrics.get_snapshot()

        total_runs = snap.get("pipeline_runs_total", 0)
        blocked    = snap.get("pipeline_blocked_total", 0)
        failures   = snap.get("pipeline_failures_total", 0)
        second_pass = snap.get("pipeline_second_pass_total", 0)
        avg_rt     = snap.get("avg_runtime_ms", 0.0)
        sec_events = snap.get("security_event_counts", {})

        pii_detected      = sec_events.get("pii_detected", 0)
        neutrality_viols  = sec_events.get("neutrality_violation", 0)
        bias_detected     = sec_events.get("bias_detected", 0)
        suspicious_allowed = sec_events.get("suspicious_input_allowed", 0)
        output_filtered   = sec_events.get("output_filtered", 0)
        injections        = sec_events.get("injection_detected", 0)

        # --- Row 1: pipeline health ---
        st.markdown("**Pipeline Health**")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Runs", total_runs)
        c2.metric("Inputs Blocked", blocked,
                  delta="attack" if blocked > 0 else None,
                  delta_color="inverse" if blocked > 0 else "off")
        c3.metric("Failures", failures,
                  delta="error" if failures > 0 else None,
                  delta_color="inverse" if failures > 0 else "off")
        c4.metric("Second-Pass Re-runs", second_pass)
        c5.metric("Avg Runtime (ms)", f"{avg_rt:.0f}")

        # Derived rate row (only meaningful once ≥1 run exists)
        if total_runs > 0:
            block_rate   = blocked   / total_runs * 100
            failure_rate = failures  / total_runs * 100
            sp_rate      = second_pass / total_runs * 100
            r1, r2, r3 = st.columns(3)
            r1.metric("Block Rate", f"{block_rate:.1f}%",
                      delta="high" if block_rate > 10 else None,
                      delta_color="inverse" if block_rate > 10 else "off")
            r2.metric("Failure Rate", f"{failure_rate:.1f}%",
                      delta="high" if failure_rate > 5 else None,
                      delta_color="inverse" if failure_rate > 5 else "off")
            r3.metric("Second-Pass Rate", f"{sp_rate:.1f}%",
                      help="% of runs where the pipeline triggered a second-pass review")

        st.divider()

        # --- Row 2: security event headline cards ---
        st.markdown("**Security Event Highlights**")
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("Injections Blocked", injections,
                  delta="blocked" if injections > 0 else None,
                  delta_color="inverse" if injections > 0 else "off")
        s2.metric("PII Detected", pii_detected,
                  delta="redacted" if pii_detected > 0 else None,
                  delta_color="inverse" if pii_detected > 0 else "off")
        s3.metric("Outputs Filtered", output_filtered)
        s4.metric("Neutrality Violations", neutrality_viols,
                  delta="flagged" if neutrality_viols > 0 else None,
                  delta_color="inverse" if neutrality_viols > 0 else "off")
        s5.metric("Bias Detected", bias_detected,
                  delta="flagged" if bias_detected > 0 else None,
                  delta_color="inverse" if bias_detected > 0 else "off")

        if suspicious_allowed > 0:
            st.warning(
                f"⚠️ **{suspicious_allowed}** suspicious input(s) were allowed through with a "
                "warning (below hard-block threshold). Review `logs/events.jsonl`."
            )

        st.divider()

        # --- Security event breakdown table + chart ---
        st.markdown("**Security Event Counts by Category**")
        if sec_events:
            event_labels = {
                "injection_detected":       "Injections Blocked",
                "suspicious_input_allowed": "Suspicious (Allowed with Warning)",
                "pii_detected":             "PII Detected & Redacted",
                "output_filtered":          "Outputs Filtered",
                "bias_detected":            "Bias / Identity Language Detected",
                "neutrality_violation":     "Neutrality Violations",
                "clean_input":              "Clean Inputs (no flags)",
                "clean_output":             "Clean Outputs (no flags)",
            }
            rows = [
                {"Event Type": event_labels.get(k, k), "Count": v,
                 "Category": "Risk" if k not in ("clean_input", "clean_output") else "Nominal"}
                for k, v in sorted(sec_events.items(), key=lambda x: -x[1])
            ]
            df_full = pd.DataFrame(rows)

            col_tbl, col_info = st.columns([3, 1])
            with col_tbl:
                st.dataframe(df_full[["Event Type", "Count"]], hide_index=True, use_container_width=True)
            with col_info:
                risk_total    = sum(r["Count"] for r in rows if r["Category"] == "Risk")
                nominal_total = sum(r["Count"] for r in rows if r["Category"] == "Nominal")
                if risk_total > 0:
                    st.error(f"**{risk_total}** total risk events")
                if nominal_total > 0:
                    st.success(f"**{nominal_total}** clean passes")

            # Bar chart: risk events only (exclude clean_* for clarity)
            risk_rows = [r for r in rows if r["Category"] == "Risk"]
            if risk_rows:
                st.markdown("**Risk Event Breakdown**")
                chart_df = pd.DataFrame(risk_rows)[["Event Type", "Count"]]
                _render_horizontal_bar_chart(chart_df, "Event Type", "Count")
        else:
            st.info("No security events recorded yet. Run the pipeline to see telemetry.")

        st.divider()

        # --- Second-pass note ---
        if second_pass > 0:
            st.info(
                f"**Autonomy second-pass re-analyses triggered:** {second_pass}  \n"
                "The pipeline flagged uncertain findings and automatically re-ran analysis "
                "for human review (IMDA Principle 2 — Human Involvement)."
            )

        # --- Recent runtime trend ---
        recent = snap.get("recent_runtimes_ms_preview", snap.get("recent_runtimes_ms", []))
        if len(recent) > 1:
            st.markdown("**Recent Pipeline Runtimes (ms)**")
            rt_df = pd.DataFrame({"Run": range(1, len(recent) + 1), "Runtime (ms)": recent})
            st.line_chart(rt_df.set_index("Run"))

    except Exception as e:
        st.warning(f"Security analytics unavailable: {e}")


# ---------------------------------------------------------------------------
# Benchmark Evaluation Metrics
# ---------------------------------------------------------------------------

def _render_eval_metrics(state: dict) -> None:
    """Render the Benchmark Evaluation Metrics panel."""
    st.subheader("Benchmark Evaluation Metrics")
    tab_run, tab_cum = st.tabs(["Analysed Transcript", "Cumulative"])

    with tab_run:
        _render_eval_metrics_run(state)

    with tab_cum:
        _render_eval_metrics_cumulative()


def _render_eval_metrics_run(state: dict) -> None:
    """Render per-transcript analysis metrics for the current run."""
    st.caption(
        "Metrics for the currently analysed transcript. Corpus-level classification metrics such as "
        "precision and recall are not meaningful for a single transcript."
    )

    inconsistencies = state.get("inconsistencies", []) or []
    explanations = state.get("explanations", []) or []
    entities = state.get("entities", []) or []
    timeline = state.get("timeline", []) or []
    input_flags = state.get("security_input_flags", []) or []
    output_flags = state.get("security_output_flags", []) or []
    high = sum(1 for i in inconsistencies if i.get("severity") == "HIGH")
    medium = sum(1 for i in inconsistencies if i.get("severity") == "MEDIUM")
    low = sum(1 for i in inconsistencies if i.get("severity") == "LOW")
    llm_count = sum(1 for i in inconsistencies if i.get("detection_method") == "llm")
    rule_count = sum(1 for i in inconsistencies if i.get("detection_method") == "rule_based")
    requires_review = bool(state.get("requires_review"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entities", len(entities))
    c2.metric("Timeline Events", len(timeline))
    c3.metric("Inconsistencies", len(inconsistencies))
    c4.metric("Explanations", len([e for e in explanations if e.get("inconsistency_id") not in ("NONE", "NO_ISSUES")]))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("High Severity", high)
    c6.metric("Medium Severity", medium)
    c7.metric("Low Severity", low)
    c8.metric("Requires Review", "Yes" if requires_review else "No")

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("LLM Findings", llm_count)
    c10.metric("Rule-Based Findings", rule_count)
    c11.metric("Input Flags", len(input_flags))
    c12.metric("Output Flags", len(output_flags))

    conf_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for exp in explanations:
        conf = (exp.get("confidence") or "").upper()
        if conf in conf_counts and exp.get("inconsistency_id") not in ("NONE", "NO_ISSUES"):
            conf_counts[conf] += 1

    st.markdown("**Current Transcript Summary**")
    summary_rows = [
        {"Metric": "Transcript status", "Value": "Blocked by input security gate" if state.get("security_input_blocked") else "Analysed"},
        {"Metric": "Second-pass review requested", "Value": "Yes" if requires_review else "No"},
        {"Metric": "Explanation confidence — HIGH", "Value": conf_counts["HIGH"]},
        {"Metric": "Explanation confidence — MEDIUM", "Value": conf_counts["MEDIUM"]},
        {"Metric": "Explanation confidence — LOW", "Value": conf_counts["LOW"]},
    ]
    st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)


def _render_eval_metrics_cumulative() -> None:
    """Render saved corpus-level benchmark metrics."""
    st.caption(
        "Precision / Recall / F1 / FPR / FNR computed over the 32-transcript labelled corpus "
        "(`sample_transcripts/`). Ground truth is derived from filename prefixes: "
        "`contradiction_*` / `inconsistent_*` / `complex_*` = Positive (issues expected); "
        "`perfect_*` = Negative (clean transcript)."
    )
    st.caption("Results are read from `logs/eval_metrics.json`.")

    # Load saved results
    if not _EVAL_METRICS_PATH.exists():
        st.info(
            "No saved evaluation results found in `logs/eval_metrics.json`."
        )
        return

    try:
        data = json.loads(_EVAL_METRICS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        st.error(f"Could not read `logs/eval_metrics.json`: {exc}")
        return

    mode          = data.get("mode", "—")
    n_transcripts = data.get("n_transcripts", 0)
    dm            = data.get("detection_metrics", {})
    pm            = data.get("performance_metrics", {})
    em            = data.get("explanation_metrics", {})
    pc            = data.get("per_category", {})

    st.caption(f"**Mode:** {mode} | **Corpus size:** {n_transcripts} transcripts")
    st.divider()

    # ------------------------------------------------------------------
    # Detection metrics — gauge bars + cards
    # ------------------------------------------------------------------
    st.markdown('<p class="section-label">Detection Performance</p>', unsafe_allow_html=True)

    precision = dm.get("precision", 0)
    recall    = dm.get("recall", 0)
    f1        = dm.get("f1_score", 0)
    accuracy  = dm.get("accuracy", 0)

    def _gauge_color(v: float) -> str:
        if v >= 0.8: return "#27ae60"
        if v >= 0.5: return "#e67e22"
        return "#c0392b"

    for label, val, help_txt in [
        ("Precision",       precision, "Of flagged transcripts, how many truly had issues"),
        ("Recall (TPR)",    recall,    "Of transcripts with issues, how many were caught"),
        ("F1-Score",        f1,        "Harmonic mean of precision and recall"),
        ("Accuracy",        accuracy,  "Overall correct predictions"),
    ]:
        col_lbl, col_bar, col_val = st.columns([2, 5, 1])
        col_lbl.markdown(
            f'<p style="font-size:0.82rem;color:#aaa;margin:6px 0">{label}</p>',
            unsafe_allow_html=True,
        )
        col_bar.markdown(
            f'<div style="background:#2a2a2a;border-radius:4px;height:12px;margin-top:10px">'
            f'<div style="background:{_gauge_color(val)};width:{val*100:.1f}%;height:12px;'
            f'border-radius:4px;transition:width 0.3s"></div></div>',
            unsafe_allow_html=True,
        )
        col_val.markdown(
            f'<p style="font-size:0.88rem;font-weight:700;color:{_gauge_color(val)};'
            f'margin:4px 0;text-align:right">{val:.2f}</p>',
            unsafe_allow_html=True,
        )

    st.divider()

    st.markdown("**Full Detection Metrics**")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Precision",
              f"{dm.get('precision', 0):.4f}",
              help="Of flagged transcripts, how many truly had issues")
    c2.metric("Recall (TPR)",
              f"{dm.get('recall', 0):.4f}",
              help="Of transcripts with issues, how many were caught")
    c3.metric("F1-Score",
              f"{dm.get('f1_score', 0):.4f}",
              help="Harmonic mean of precision and recall")
    c4.metric("Accuracy",
              f"{dm.get('accuracy', 0):.4f}",
              help="Overall correct predictions")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("False Positive Rate",
              f"{dm.get('false_positive_rate', 0):.4f}",
              delta="FP risk" if dm.get("false_positive_rate", 0) > 0.1 else None,
              delta_color="inverse" if dm.get("false_positive_rate", 0) > 0.1 else "off",
              help="Of clean transcripts, how many were wrongly flagged")
    c6.metric("False Negative Rate",
              f"{dm.get('false_negative_rate', 0):.4f}",
              help="Of transcripts with issues, how many were missed")
    c7.metric("Specificity (TNR)",
              f"{dm.get('specificity', 0):.4f}",
              help="Ability to correctly identify clean transcripts")
    c8.metric("",
              "",
              help="")

    # Confusion matrix
    st.markdown("**Confusion Matrix**")
    tp = dm.get("true_positives", 0)
    fp = dm.get("false_positives", 0)
    tn = dm.get("true_negatives", 0)
    fn = dm.get("false_negatives", 0)
    cm1, cm2, cm3, cm4 = st.columns(4)
    cm1.metric("True Positives (TP)", tp,  help="Correctly detected transcripts with issues")
    cm2.metric("False Positives (FP)", fp, help="Clean transcripts wrongly flagged")
    cm3.metric("True Negatives (TN)", tn,  help="Clean transcripts correctly cleared")
    cm4.metric("False Negatives (FN)", fn, help="Transcripts with issues that were missed")

    st.divider()

    # ------------------------------------------------------------------
    # Per-category breakdown
    # ------------------------------------------------------------------
    st.markdown("**Per-Category Breakdown**")

    cat_rows = []
    for cat, m in pc.items():
        if "recall" in m:
            cat_rows.append({
                "Category":  cat,
                "Role":      "Positive (issues expected)",
                "Total":     m["total"],
                "Detected":  m["detected"],
                "Recall":    m["recall"],
                "Specificity": "—",
            })
        else:
            cat_rows.append({
                "Category":   cat,
                "Role":       "Negative (should be clean)",
                "Total":      m["total"],
                "Detected":   m.get("false_positives", 0),
                "Recall":     "—",
                "Specificity": m.get("specificity", 0),
            })

    if cat_rows:
        df_cat = pd.DataFrame(cat_rows)
        st.dataframe(
            df_cat,
            column_config={
                "Category":    st.column_config.TextColumn("Category", width="small"),
                "Role":        st.column_config.TextColumn("Role", width="medium"),
                "Total":       st.column_config.NumberColumn("Total"),
                "Detected":    st.column_config.NumberColumn("Detected"),
                "Recall":      st.column_config.NumberColumn("Recall", format="%.4f"),
                "Specificity": st.column_config.NumberColumn("Specificity", format="%.4f"),
            },
            hide_index=True,
            use_container_width=True,
        )

        # Bar chart: recall per positive category
        recall_data = {r["Category"]: r["Recall"] for r in cat_rows if r["Recall"] != "—"}
        if recall_data:
            st.markdown("**Recall by Category (positive classes)**")
            recall_df = pd.DataFrame(
                [{"Category": k, "Recall": v} for k, v in recall_data.items()]
            )
            _render_horizontal_bar_chart(recall_df, "Category", "Recall", min_height=180)

    if mode and "Rule-based" in mode:
        st.info(
            "**Note:** The rule-based path only detects temporal contradictions (date/time mismatches). "
            "Low recall is expected for this mode — the LLM path is required for semantic, factual, "
            "and contextual inconsistency detection. Run with `--model 'Claude Sonnet 4.6 (Anthropic)'` "
            "to benchmark the full LLM path."
        )

    st.divider()

    # ------------------------------------------------------------------
    # Explanation quality metrics
    # ------------------------------------------------------------------
    st.markdown("**Explanation Quality Metrics** *(proxy — no human annotation required)*")

    total_expl = em.get("total_explanations", 0)
    st.caption(f"Based on {total_expl} explanation(s) generated across the evaluation corpus.")

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Quote Population Rate",
              f"{em.get('quote_population_rate', 0):.0%}",
              help="Explanations that include ≥1 evidence quote from the transcript")
    e2.metric("Recommendation Rate",
              f"{em.get('recommendation_rate', 0):.0%}",
              help="Explanations that include a follow-up action recommendation")
    e3.metric("ReAct Completeness",
              f"{em.get('react_completeness_rate', 0):.0%}",
              help="Explanations where both Observe and Reason fields are populated (LLM path only)")
    e4.metric("Neutrality Pass Rate",
              f"{em.get('neutrality_pass_rate', 0):.0%}",
              help="Pipeline runs with zero output security flags")

    cd = em.get("confidence_distribution", {})
    if cd:
        st.markdown("**Confidence Distribution**")
        conf_df = pd.DataFrame({
            "Confidence Level": ["HIGH", "MEDIUM", "LOW"],
            "Rate": [cd.get("HIGH", 0), cd.get("MEDIUM", 0), cd.get("LOW", 0)],
        })
        _render_horizontal_bar_chart(conf_df, "Confidence Level", "Rate", min_height=180, label_limit=180)

    st.divider()

    # ------------------------------------------------------------------
    # Performance metrics
    # ------------------------------------------------------------------
    st.markdown("**Performance Metrics**")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Avg Time / Transcript", f"{pm.get('avg_time_s', 0):.3f}s")
    p2.metric("Min Time", f"{pm.get('min_time_s', 0):.3f}s")
    p3.metric("Max Time", f"{pm.get('max_time_s', 0):.3f}s")
    p4.metric("Total Evaluation Time", f"{pm.get('total_time_s', 0):.1f}s")


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
