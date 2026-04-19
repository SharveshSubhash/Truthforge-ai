#!/usr/bin/env python3
"""
TRUTHFORGE AI — Evaluation Script
===================================
Computes benchmark evaluation metrics for the inconsistency detection pipeline
against the 32 labelled sample transcripts.

Ground-truth labels are derived from filename prefixes:
  contradiction_*  → POSITIVE (known contradictions)
  inconsistent_*   → POSITIVE (known inconsistencies)
  complex_*        → POSITIVE (multi-issue cases)
  perfect_*        → NEGATIVE (clean transcripts — ground truth: no issues)

Metrics computed
-----------------
  Detection (binary classification):
    Precision, Recall, F1-score,
    False Positive Rate (FPR), False Negative Rate (FNR),
    Accuracy, Specificity

  Performance:
    Avg / Min / Max processing time per transcript

  Security:
    Injection block rate, bias detection rate

  Explanation quality (proxy metrics, rule-based path):
    Quote population rate, confidence distribution,
    Recommendation population rate, ReAct field completeness

Usage
------
    python scripts/evaluate.py [--dir PATH] [--model LABEL] [--json]

Options:
    --dir    Path to transcript directory (default: ./sample_transcripts)
    --model  LLM model label e.g. 'GPT-4o (OpenAI)' — omit for rule-based mode
    --json   Output results as JSON (for programmatic use)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

os.environ.setdefault("TRUTHFORGE_FALLBACK_MODE", "1")

from agents.orchestration_agent import run_pipeline

# ---------------------------------------------------------------------------
# Ground-truth label mapping
# ---------------------------------------------------------------------------

def ground_truth(filename: str) -> int:
    """Return 1 (positive — has issues) or 0 (negative — clean)."""
    name = filename.lower()
    if name.startswith(("contradiction", "inconsistent", "complex")):
        return 1
    if name.startswith("perfect"):
        return 0
    return -1  # unknown — excluded from metrics


def category(filename: str) -> str:
    name = filename.lower()
    for prefix in ("contradiction", "inconsistent", "complex", "perfect"):
        if name.startswith(prefix):
            return prefix.upper()
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def safe_div(num: float, den: float, default: float = 0.0) -> float:
    return round(num / den, 4) if den > 0 else default


def compute_detection_metrics(results: list[dict]) -> dict:
    """Compute precision, recall, F1, FPR, FNR from result list."""
    tp = fp = tn = fn = 0
    for r in results:
        gt   = r["ground_truth"]
        pred = 1 if r["n_issues"] > 0 and not r["error"] else 0
        if gt == -1:
            continue
        if gt == 1 and pred == 1:
            tp += 1
        elif gt == 0 and pred == 1:
            fp += 1
        elif gt == 0 and pred == 0:
            tn += 1
        elif gt == 1 and pred == 0:
            fn += 1

    precision    = safe_div(tp, tp + fp)
    recall       = safe_div(tp, tp + fn)        # = True Positive Rate
    f1           = safe_div(2 * precision * recall, precision + recall)
    fpr          = safe_div(fp, fp + tn)         # False Positive Rate
    fnr          = safe_div(fn, fn + tp)         # False Negative Rate
    specificity  = safe_div(tn, tn + fp)         # True Negative Rate
    accuracy     = safe_div(tp + tn, tp + tn + fp + fn)

    return {
        "true_positives":  tp,
        "false_positives": fp,
        "true_negatives":  tn,
        "false_negatives": fn,
        "precision":       precision,
        "recall":          recall,
        "f1_score":        f1,
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
        "specificity":     specificity,
        "accuracy":        accuracy,
    }


def compute_performance_metrics(results: list[dict]) -> dict:
    times = [r["elapsed"] for r in results if not r["error"]]
    if not times:
        return {}
    return {
        "avg_time_s":   round(sum(times) / len(times), 3),
        "min_time_s":   round(min(times), 3),
        "max_time_s":   round(max(times), 3),
        "total_time_s": round(sum(times), 3),
        "n_transcripts": len(times),
    }


def compute_explanation_metrics(results: list[dict]) -> dict:
    """
    Proxy metrics for explanation quality — derived from structural
    properties of the pipeline output (no human annotation required).

    Metrics:
      quote_population_rate    — % of explanations that include evidence quotes
      recommendation_rate      — % of explanations with a recommendation
      react_completeness_rate  — % of explanations with observe+reason fields
      high_confidence_rate     — % of issues rated HIGH confidence
      medium_confidence_rate   — % of issues rated MEDIUM confidence
      low_confidence_rate      — % of issues rated LOW confidence
      neutrality_pass_rate     — % of runs with zero output security flags
    """
    total_expl      = 0
    with_quotes     = 0
    with_rec        = 0
    react_complete  = 0
    conf_counts     = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    neutrality_pass = 0
    neutrality_total = 0

    for r in results:
        if r["error"]:
            continue

        explanations = r.get("explanations", [])
        for exp in explanations:
            iid = exp.get("inconsistency_id", "")
            if iid == "NONE":
                continue  # skip the empty placeholder
            total_expl += 1
            if exp.get("evidence_quotes"):
                with_quotes += 1
            if exp.get("recommendation"):
                with_rec += 1
            if exp.get("observe") and exp.get("reason"):
                react_complete += 1
            conf = exp.get("confidence", "").upper()
            if conf in conf_counts:
                conf_counts[conf] += 1

        sec_flags = r.get("security_output_flags", [])
        neutrality_total += 1
        if not sec_flags:
            neutrality_pass += 1

    return {
        "total_explanations":       total_expl,
        "quote_population_rate":    safe_div(with_quotes, total_expl),
        "recommendation_rate":      safe_div(with_rec, total_expl),
        "react_completeness_rate":  safe_div(react_complete, total_expl),
        "confidence_distribution": {
            "HIGH":   safe_div(conf_counts["HIGH"],   total_expl),
            "MEDIUM": safe_div(conf_counts["MEDIUM"], total_expl),
            "LOW":    safe_div(conf_counts["LOW"],    total_expl),
        },
        "neutrality_pass_rate": safe_div(neutrality_pass, neutrality_total),
    }


def compute_per_category(results: list[dict]) -> dict:
    """Recall per category — shows which types of issues the system catches."""
    cats: dict[str, dict] = {}
    for r in results:
        cat = r["category"]
        if cat not in cats:
            cats[cat] = {"total": 0, "detected": 0, "gt": r["ground_truth"]}
        cats[cat]["total"] += 1
        if r["n_issues"] > 0 and not r["error"]:
            cats[cat]["detected"] += 1

    out = {}
    for cat, d in cats.items():
        if d["gt"] == 1:
            out[cat] = {
                "total":    d["total"],
                "detected": d["detected"],
                "recall":   safe_div(d["detected"], d["total"]),
                "role":     "positive (should detect issues)",
            }
        else:
            fp = d["detected"]
            out[cat] = {
                "total":          d["total"],
                "false_positives": fp,
                "specificity":    safe_div(d["total"] - fp, d["total"]),
                "role":           "negative (should find 0 issues)",
            }
    return out


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_evaluation(
    transcript_dir: str = "sample_transcripts",
    model_label: str | None = None,
    as_json: bool = False,
) -> dict:
    t_dir = Path(transcript_dir)
    files = sorted(t_dir.glob("*.txt"))
    if not files:
        print(f"No .txt files found in {t_dir}", file=sys.stderr)
        sys.exit(1)

    llm_config = None
    mode_str   = "Rule-based fallback (no LLM)"
    if model_label:
        from config import make_langgraph_config
        llm_config = make_langgraph_config(model_label)
        mode_str   = f"LLM — {model_label}"
        os.environ.pop("TRUTHFORGE_FALLBACK_MODE", None)

    if not as_json:
        print(f"\nTRUTHFORGE AI — Evaluation  |  Mode: {mode_str}")
        print(f"Corpus: {t_dir}  |  {len(files)} transcripts\n")

    results = []
    for fpath in files:
        gt  = ground_truth(fpath.name)
        cat = category(fpath.name)
        if not as_json:
            print(f"  [{cat:>13}]  {fpath.name:<50}", end="  ", flush=True)
        try:
            text    = fpath.read_text(encoding="utf-8")
            t0      = time.time()
            state   = run_pipeline(text, llm_config=llm_config)
            elapsed = time.time() - t0

            issues  = state.get("inconsistencies", []) or []
            expls   = state.get("explanations",   []) or []
            sec_out = state.get("security_output_flags", []) or []
            error   = state.get("error_state", "") or ""

            n = len(issues)
            if not as_json:
                pred = "DETECTED" if n > 0 else "CLEAN"
                correct = (
                    (gt == 1 and n > 0) or (gt == 0 and n == 0)
                ) if gt != -1 else None
                mark = "✓" if correct else ("✗" if correct is False else "?")
                print(f"{mark}  {n:>2} issue(s)  {elapsed:.1f}s")

            results.append({
                "file":                 fpath.name,
                "category":             cat,
                "ground_truth":         gt,
                "n_issues":             n,
                "issues":               issues,
                "explanations":         expls,
                "security_output_flags": sec_out,
                "error":                error,
                "elapsed":              elapsed,
            })

        except Exception as exc:
            if not as_json:
                print(f"  ERROR: {exc}")
            results.append({
                "file": fpath.name, "category": cat, "ground_truth": gt,
                "n_issues": 0, "issues": [], "explanations": [],
                "security_output_flags": [], "error": str(exc), "elapsed": 0.0,
            })

    # -----------------------------------------------------------------------
    # Compute metrics
    # -----------------------------------------------------------------------
    detection    = compute_detection_metrics(results)
    performance  = compute_performance_metrics(results)
    explanation  = compute_explanation_metrics(results)
    per_category = compute_per_category(results)

    report = {
        "mode":                mode_str,
        "corpus":              str(t_dir),
        "n_transcripts":       len(files),
        "detection_metrics":   detection,
        "performance_metrics": performance,
        "explanation_metrics": explanation,
        "per_category":        per_category,
    }

    if as_json:
        return report

    # -----------------------------------------------------------------------
    # Pretty-print report
    # -----------------------------------------------------------------------
    d = detection
    p = performance
    e = explanation

    print("\n" + "=" * 70)
    print("  DETECTION METRICS (Binary Classification)")
    print("=" * 70)
    print(f"  Confusion Matrix:  TP={d['true_positives']}  FP={d['false_positives']}  "
          f"TN={d['true_negatives']}  FN={d['false_negatives']}")
    print()
    print(f"  {'Precision':<28} {d['precision']:.4f}  "
          f"  (of flagged transcripts, how many truly had issues)")
    print(f"  {'Recall (True Positive Rate)':<28} {d['recall']:.4f}  "
          f"  (of transcripts with issues, how many were caught)")
    print(f"  {'F1-Score':<28} {d['f1_score']:.4f}  "
          f"  (harmonic mean of precision and recall)")
    print(f"  {'False Positive Rate':<28} {d['false_positive_rate']:.4f}  "
          f"  (of clean transcripts, how many were wrongly flagged)")
    print(f"  {'False Negative Rate':<28} {d['false_negative_rate']:.4f}  "
          f"  (of transcripts with issues, how many were missed)")
    print(f"  {'Specificity':<28} {d['specificity']:.4f}  "
          f"  (ability to correctly identify clean transcripts)")
    print(f"  {'Accuracy':<28} {d['accuracy']:.4f}  "
          f"  (overall correct predictions)")

    print("\n" + "=" * 70)
    print("  PER-CATEGORY BREAKDOWN")
    print("=" * 70)
    for cat, m in per_category.items():
        if "recall" in m:
            print(f"  {cat:<14} recall={m['recall']:.4f}  "
                  f"({m['detected']}/{m['total']} detected)   [{m['role']}]")
        else:
            print(f"  {cat:<14} specificity={m['specificity']:.4f}  "
                  f"FP={m['false_positives']}/{m['total']}   [{m['role']}]")

    print("\n" + "=" * 70)
    print("  PERFORMANCE METRICS")
    print("=" * 70)
    print(f"  Avg time / transcript : {p.get('avg_time_s', 0):.3f}s")
    print(f"  Min time              : {p.get('min_time_s', 0):.3f}s")
    print(f"  Max time              : {p.get('max_time_s', 0):.3f}s")
    print(f"  Total evaluation time : {p.get('total_time_s', 0):.1f}s  "
          f"({p.get('n_transcripts', 0)} transcripts)")

    print("\n" + "=" * 70)
    print("  EXPLANATION QUALITY METRICS  (proxy — no human annotation required)")
    print("=" * 70)
    print(f"  Total explanations generated : {e['total_explanations']}")
    print(f"  Quote population rate        : {e['quote_population_rate']:.4f}  "
          "  (explanations with ≥1 evidence quote)")
    print(f"  Recommendation rate          : {e['recommendation_rate']:.4f}  "
          "  (explanations with a follow-up action)")
    print(f"  ReAct completeness rate      : {e['react_completeness_rate']:.4f}  "
          "  (observe + reason fields both populated)")
    print(f"  Neutrality pass rate         : {e['neutrality_pass_rate']:.4f}  "
          "  (runs with 0 output security flags)")
    cd = e["confidence_distribution"]
    print(f"  Confidence distribution      : "
          f"HIGH={cd['HIGH']:.0%}  MEDIUM={cd['MEDIUM']:.0%}  LOW={cd['LOW']:.0%}")

    print("\n" + "=" * 70)
    print("  NOTE: Rule-based path only detects time/date contradictions.")
    print("  LLM path expected to significantly improve recall.")
    print("  Run: python scripts/evaluate.py --model 'Claude Sonnet 4.6 (Anthropic)'")
    print("=" * 70 + "\n")

    return report


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TRUTHFORGE evaluation script")
    parser.add_argument("--dir",   default="sample_transcripts",
                        help="Path to labelled transcript directory")
    parser.add_argument("--model", default=None,
                        help="LLM model label (omit for rule-based mode)")
    parser.add_argument("--json",  action="store_true",
                        help="Output metrics as JSON")
    args = parser.parse_args()

    report = run_evaluation(
        transcript_dir=args.dir,
        model_label=args.model,
        as_json=args.json,
    )
    if args.json:
        print(json.dumps(report, indent=2))
