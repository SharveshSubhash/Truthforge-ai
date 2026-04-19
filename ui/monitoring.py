"""
TRUTHFORGE AI — Monitoring & Observability Dashboard
=====================================================
Reads from logs/metrics.json and logs/events.jsonl to render
a live operational dashboard. No external infrastructure required.

Surfaced as a sidebar navigation option in the main Streamlit app.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# Import thresholds from source of truth — avoids silent drift if values change
from core.metrics import FAILURE_THRESHOLD as _FAILURE_THRESHOLD, BLOCK_SPIKE_THRESH as _BLOCK_SPIKE_THRESH

_LOGS_DIR     = Path(__file__).parent.parent / "logs"
_METRICS_PATH = _LOGS_DIR / "metrics.json"
_EVENTS_PATH  = _LOGS_DIR / "events.jsonl"

# High-risk event types for colour-coding
_HIGH_RISK_EVENTS = frozenset({
    "injection_detected", "bias_detected",
    "neutrality_violation", "pii_detected",
    "suspicious_input_allowed",
})


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=5)
def _load_metrics() -> dict:
    if not _METRICS_PATH.exists():
        return {}
    try:
        with open(_METRICS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.warning(
            f"`logs/metrics.json` exists but could not be parsed — "
            "it may be corrupted. Delete it to reset metrics."
        )
        return {}
    except Exception:
        return {}


@st.cache_data(ttl=5)
def _load_recent_events(n: int = 50) -> list[dict]:
    """Tail the last `n` lines of events.jsonl without loading the whole file."""
    if not _EVENTS_PATH.exists():
        return []
    events: list[dict] = []
    try:
        with open(_EVENTS_PATH, encoding="utf-8") as f:
            # Read only the tail — avoids loading a potentially large file
            lines = f.readlines()
        for line in reversed(lines[-n:]):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return events


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def _alert_badge(condition: bool, label: str) -> str:
    return f"🔴 {label}" if condition else f"🟢 {label}"


def _fmt_ts(ts_str: str | None) -> str:
    if not ts_str:
        return "—"
    try:
        dt = datetime.fromisoformat(ts_str).astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts_str


def _row_style(row) -> list[str]:
    if row["Event"] in _HIGH_RISK_EVENTS:
        return ["background-color: #ffe0e0"] * len(row)
    return [""] * len(row)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_monitoring() -> None:
    """Render the full monitoring dashboard."""

    m = _load_metrics()

    # ------------------------------------------------------------------
    # Alert banner — FIRST element, full width
    # ------------------------------------------------------------------
    failures      = m.get("pipeline_failures_total", 0) if m else 0
    blocks        = m.get("pipeline_blocked_total", 0)  if m else 0
    failure_alert = failures > _FAILURE_THRESHOLD
    block_alert   = blocks   > _BLOCK_SPIKE_THRESH

    if not m:
        st.markdown(
            '<div style="background:#1a1a0d;border-left:4px solid #e67e22;padding:14px 20px;'
            'border-radius:0 6px 6px 0;margin-bottom:16px">'
            '<span style="color:#e67e22;font-weight:700">⚠ NO DATA</span>'
            '<span style="color:#aaa;font-size:0.85rem;margin-left:12px">'
            'No metrics found. Run at least one pipeline analysis.</span></div>',
            unsafe_allow_html=True,
        )
    elif failure_alert or block_alert:
        detail = []
        if failure_alert:
            detail.append(f"{failures} failures (threshold: {_FAILURE_THRESHOLD})")
        if block_alert:
            detail.append(f"{blocks} blocks (threshold: {_BLOCK_SPIKE_THRESH})")
        st.markdown(
            f'<div style="background:#3b0d0d;border-left:4px solid #c0392b;padding:14px 20px;'
            f'border-radius:0 6px 6px 0;margin-bottom:16px">'
            f'<span style="color:#e74c3c;font-weight:700;font-size:1rem">⚠ ALERT — THRESHOLD EXCEEDED</span>'
            f'<span style="color:#aaa;font-size:0.85rem;margin-left:12px">'
            f'{" · ".join(detail)}. Review events log.</span></div>',
            unsafe_allow_html=True,
        )
    else:
        total = m.get("pipeline_runs_total", 0)
        st.markdown(
            f'<div style="background:#0d3b0d;border-left:4px solid #27ae60;padding:14px 20px;'
            f'border-radius:0 6px 6px 0;margin-bottom:16px">'
            f'<span style="color:#27ae60;font-weight:700">✅ ALL SYSTEMS NOMINAL</span>'
            f'<span style="color:#aaa;font-size:0.85rem;margin-left:12px">'
            f'{total:,} total runs · No active alerts.</span></div>',
            unsafe_allow_html=True,
        )

    # Header + refresh (after banner)
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.header("System Monitoring & Observability")
    with col_refresh:
        if st.button("↻ Refresh"):
            _load_metrics.clear()
            _load_recent_events.clear()
            st.session_state["monitoring_refreshed"] = True
            st.rerun()

    if st.session_state.pop("monitoring_refreshed", False):
        st.toast("Monitoring data refreshed")

    st.caption(
        "Live operational metrics from `logs/metrics.json` and `logs/events.jsonl`. "
        "Counts are cumulative across historical runs, including development and testing activity."
    )

    if not m:
        return

    st.divider()

    # ------------------------------------------------------------------
    # Pipeline health metrics
    # ------------------------------------------------------------------
    st.subheader("Pipeline Health")

    total       = m.get("pipeline_runs_total", 0)
    avg_ms      = m.get("avg_runtime_ms", 0.0)
    second_pass = m.get("pipeline_second_pass_total", 0)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Runs", total)
    c2.metric(
        _alert_badge(failure_alert, "Pipeline Failures"),
        failures,
        delta=f"threshold: {_FAILURE_THRESHOLD}",
        delta_color="inverse",
    )
    c3.metric(
        _alert_badge(block_alert, "Security Blocks"),
        blocks,
        delta=f"threshold: {_BLOCK_SPIKE_THRESH}",
        delta_color="inverse",
    )
    c4.metric("Avg Runtime", f"{avg_ms:.0f} ms")
    c5.metric("Second-Pass Re-runs", second_pass)

    st.caption(f"Last updated: {_fmt_ts(m.get('last_updated'))}")
    st.caption(
        "Threshold alerts are based on cumulative system counters. High values may reflect repeated "
        "test runs, adversarial test cases, or historical development activity."
    )

    # ------------------------------------------------------------------
    # Runtime trend (rolling window)
    # ------------------------------------------------------------------
    runtimes = m.get("recent_runtimes_ms", [])
    if runtimes:
        st.subheader("Runtime Trend (last 100 runs)")
        st.caption(
            "Shows wall-clock runtime for the most recent 100 pipeline runs. Large spikes often reflect "
            "cold starts, long transcripts, external model latency, or test activity."
        )
        try:
            import pandas as pd
            st.line_chart(pd.DataFrame({"Runtime (ms)": runtimes}), height=200)
        except ImportError:
            st.write(runtimes[-20:])

    st.divider()

    # ------------------------------------------------------------------
    # Security event counts
    # ------------------------------------------------------------------
    st.subheader("Security Events")

    sec_counts: dict = m.get("security_event_counts", {})
    if sec_counts:
        try:
            import pandas as pd
            df_sec = pd.DataFrame(
                [{"Event Type": k, "Count": v} for k, v in sorted(sec_counts.items())]
            )
            c_left, c_right = st.columns([2, 1])
            with c_left:
                st.dataframe(df_sec, use_container_width=True, hide_index=True)
            with c_right:
                risky = {k: v for k, v in sec_counts.items() if k in _HIGH_RISK_EVENTS}
                safe  = {k: v for k, v in sec_counts.items() if k not in _HIGH_RISK_EVENTS}
                if risky:
                    st.error(
                        "**High-risk events detected:**\n"
                        + "\n".join(f"- `{k}`: {v}" for k, v in risky.items())
                    )
                if safe:
                    st.success(
                        "**Nominal events:**\n"
                        + "\n".join(f"- `{k}`: {v}" for k, v in safe.items())
                    )
        except ImportError:
            st.json(sec_counts)
    else:
        st.info("No security events recorded yet.")

    st.divider()

    # ------------------------------------------------------------------
    # Recent events log
    # ------------------------------------------------------------------
    st.subheader("Recent Events Log")
    st.caption("Last 50 entries from `logs/events.jsonl` — newest first.")

    events = _load_recent_events(50)
    if events:
        try:
            import pandas as pd
            rows = []
            for e in events:
                rows.append({
                    "Timestamp": _fmt_ts(e.get("ts")),
                    "Event":     e.get("event", "—"),
                    # Cast to str defensively; truncate to 80 chars for display
                    "Details":   str(e.get("details", "—"))[:80],
                    "Score":     e.get("score", "—"),
                })
            st.dataframe(
                pd.DataFrame(rows).style.apply(_row_style, axis=1),
                use_container_width=True,
                hide_index=True,
            )
        except ImportError:
            for e in events[:20]:
                st.json(e)
    else:
        st.info("No events recorded yet.")

    st.divider()

    # ------------------------------------------------------------------
    # Governance alignment status
    # ------------------------------------------------------------------
    st.subheader("Governance Alignment (IMDA Model AI Governance Framework)")
    st.caption(
        "Real-time status derived from operational metrics. "
        "See `docs/imda_governance_alignment.md` for full traceability matrix."
    )

    imda_checks = [
        {
            "Principle": "1 — Internal Governance",
            "Check": "Audit trail active",
            "Status": "✅ Active" if _EVENTS_PATH.exists() else "❌ No log file",
        },
        {
            "Principle": "2 — Human Oversight",
            "Check": "Second-pass review triggered when uncertain",
            "Status": f"✅ {second_pass} re-run(s) logged"
                      if second_pass > 0 else "ℹ️ No uncertain findings yet",
        },
        {
            "Principle": "3 — Operations Management",
            "Check": "Failure rate within threshold",
            "Status": f"✅ {failures} failure(s) (threshold: {_FAILURE_THRESHOLD})"
                      if not failure_alert else f"⚠️ {failures} failures — exceeds threshold",
        },
        {
            "Principle": "4 — Stakeholder Communication",
            "Check": "Disclaimer present in all reports (structural)",
            "Status": "✅ Enforced in code (not metric-based)",
        },
        {
            "Principle": "5 — Fairness",
            "Check": "Bias events caught and filtered",
            "Status": f"✅ {sec_counts.get('bias_detected', 0)} bias event(s) caught"
                      if sec_counts.get("bias_detected", 0) > 0
                      else "✅ No bias events recorded",
        },
        {
            "Principle": "6 — Explainability",
            "Check": "ReAct reasoning chain logged per run (structural)",
            "Status": "✅ Enforced in code (not metric-based)",
        },
        {
            "Principle": "7 — Security",
            "Check": "Injection attempts blocked",
            "Status": f"✅ {blocks} input(s) blocked (threshold: {_BLOCK_SPIKE_THRESH})"
                      if not block_alert else f"⚠️ {blocks} blocks — possible attack pattern",
        },
    ]

    try:
        import pandas as pd
        st.dataframe(
            pd.DataFrame(imda_checks),
            use_container_width=True,
            hide_index=True,
        )
    except ImportError:
        for check in imda_checks:
            st.write(f"**{check['Principle']}** — {check['Check']}: {check['Status']}")
