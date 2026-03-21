#!/usr/bin/env python3
"""
TRUTHFORGE AI — Batch Test Runner
==================================
Runs all transcripts in sample_transcripts/ through the full pipeline
in rule-based (no LLM) mode and prints a summary report.

Usage:
    python batch_test.py [--verbose] [--dir PATH]

Options:
    --verbose   Print per-transcript details (inconsistency text)
    --dir PATH  Path to transcript directory (default: ./sample_transcripts)
"""

from __future__ import annotations
import sys
import os
import time
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — make sure we can import from the project root
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

os.environ.setdefault("TRUTHFORGE_FALLBACK_MODE", "1")

from agents.orchestration_agent import run_pipeline

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def c(colour: str, text: str) -> str:
    return f"{colour}{text}{RESET}"

# ---------------------------------------------------------------------------
# Expected labels from filename prefixes
# ---------------------------------------------------------------------------
def expected_label(filename: str) -> str:
    name = filename.lower()
    if name.startswith("contradiction"):
        return "CONTRADICTION"
    if name.startswith("inconsistent"):
        return "INCONSISTENT"
    if name.startswith("perfect"):
        return "PERFECT"
    if name.startswith("complex"):
        return "COMPLEX"
    return "UNKNOWN"

# ---------------------------------------------------------------------------
# Main batch runner
# ---------------------------------------------------------------------------
def run_batch(transcript_dir: str, verbose: bool = False, model_label: str | None = None) -> None:
    t_dir = Path(transcript_dir)
    files = sorted(t_dir.glob("*.txt"))

    if not files:
        print(c(RED, f"No .txt files found in {t_dir}"))
        sys.exit(1)

    # Build LLM config if a model label was supplied
    llm_config = None
    mode_str   = "Rule-based fallback (no LLM)"
    if model_label:
        from config import make_langgraph_config
        llm_config = make_langgraph_config(model_label)
        mode_str   = f"LLM — {model_label}"
        os.environ.pop("TRUTHFORGE_FALLBACK_MODE", None)   # ensure LLM path is used

    print()
    print(c(BOLD + CYAN, "=" * 72))
    print(c(BOLD + CYAN, "  TRUTHFORGE AI — BATCH TEST RUNNER"))
    print(c(BOLD + CYAN, "=" * 72))
    print(f"  Directory : {t_dir}")
    print(f"  Files     : {len(files)}")
    print(f"  Mode      : {mode_str}")
    print(c(CYAN, "=" * 72))
    print()

    results = []
    errors  = []

    for i, fpath in enumerate(files, 1):
        label = expected_label(fpath.name)
        print(f"[{i:02d}/{len(files)}] {c(BOLD, fpath.name)}", end="  ", flush=True)

        try:
            text = fpath.read_text(encoding="utf-8")
            t0   = time.time()
            state = run_pipeline(text, llm_config=llm_config)
            elapsed = time.time() - t0

            issues = state.get("inconsistencies", []) or []
            n      = len(issues)
            error  = state.get("error_state", "")

            if error:
                status = c(RED, f"ERROR: {error[:60]}")
                errors.append((fpath.name, error))
            elif n == 0:
                status = c(GREEN, "✓  0 inconsistencies")
            else:
                severities = [iss.get("severity", "?").upper() for iss in issues]
                sev_str = ", ".join(severities[:5]) + ("…" if len(severities) > 5 else "")
                status = c(YELLOW, f"⚠  {n} inconsistenc{'y' if n==1 else 'ies'}  [{sev_str}]")

            print(f"{status}  ({elapsed:.1f}s)")

            results.append({
                "file"     : fpath.name,
                "label"    : label,
                "count"    : n,
                "issues"   : issues,
                "error"    : error,
                "elapsed"  : elapsed,
            })

            if verbose and issues:
                for iss in issues:
                    itype = iss.get("type", "?")
                    sev   = iss.get("severity", "?").upper()
                    desc  = (iss.get("explanation") or iss.get("description") or "")[:100]
                    print(f"         {c(YELLOW,'→')} [{sev}] {itype}: {desc}")

        except Exception as exc:
            print(c(RED, f"EXCEPTION: {exc}"))
            errors.append((fpath.name, str(exc)))
            results.append({
                "file": fpath.name, "label": label,
                "count": 0, "issues": [], "error": str(exc), "elapsed": 0,
            })

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print()
    print(c(BOLD + CYAN, "=" * 72))
    print(c(BOLD + CYAN, "  SUMMARY"))
    print(c(CYAN, "=" * 72))

    total       = len(results)
    with_issues = sum(1 for r in results if r["count"] > 0 and not r["error"])
    clean       = sum(1 for r in results if r["count"] == 0 and not r["error"])
    err_count   = sum(1 for r in results if r["error"])
    total_found = sum(r["count"] for r in results)
    avg_time    = sum(r["elapsed"] for r in results) / total if total else 0

    print(f"  Total files       : {total}")
    print(f"  With issues found : {c(YELLOW, str(with_issues))}")
    print(f"  Clean (0 issues)  : {c(GREEN,  str(clean))}")
    print(f"  Errors            : {c(RED,    str(err_count))}")
    print(f"  Total issues found: {c(BOLD,   str(total_found))}")
    print(f"  Avg time/file     : {avg_time:.1f}s")

    # Per-category breakdown
    print()
    print(c(BOLD, "  Per-category detection:"))
    for cat in ["CONTRADICTION", "INCONSISTENT", "PERFECT", "COMPLEX"]:
        cat_results = [r for r in results if r["label"] == cat]
        if not cat_results:
            continue
        flagged  = sum(1 for r in cat_results if r["count"] > 0)
        clean_c  = sum(1 for r in cat_results if r["count"] == 0 and not r["error"])
        total_c  = len(cat_results)

        if cat == "PERFECT":
            # For perfect, we WANT 0 flags — false positives are bad
            fp = flagged
            bar = c(GREEN if fp == 0 else RED, f"{clean_c}/{total_c} clean (FP={fp})")
        else:
            # For contradiction/inconsistent/complex we WANT flags
            tp = flagged
            bar = c(GREEN if tp > 0 else RED, f"{flagged}/{total_c} flagged")

        print(f"    {cat:<14} : {bar}")

    # Detailed table
    print()
    print(c(BOLD, "  Per-file results:"))
    print(f"  {'#':<3} {'File':<46} {'Exp':<14} {'Issues':>6}  {'Time':>5}")
    print(f"  {'-'*3} {'-'*46} {'-'*14} {'-'*6}  {'-'*5}")

    for i, r in enumerate(results, 1):
        fname  = r["file"][:45]
        label  = r["label"]
        cnt    = r["count"]
        t_s    = f"{r['elapsed']:.1f}s"
        err    = r["error"]

        if err:
            cnt_str = c(RED, "ERROR")
        elif cnt == 0:
            cnt_str = c(GREEN, "  0   ")
        else:
            cnt_str = c(YELLOW, f"  {cnt:<4}")

        print(f"  {i:<3} {fname:<46} {label:<14} {cnt_str}  {t_s:>5}")

    if errors:
        print()
        print(c(RED + BOLD, "  ERRORS:"))
        for fname, msg in errors:
            print(f"    {fname}: {msg[:80]}")

    print()
    print(c(CYAN, "=" * 72))
    print(c(BOLD, "  Batch test complete."))
    print(c(CYAN, "=" * 72))
    print()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TRUTHFORGE batch test runner")
    parser.add_argument("--verbose", action="store_true",
                        help="Print individual inconsistency details")
    parser.add_argument("--dir", default="sample_transcripts",
                        help="Path to transcript directory")
    parser.add_argument("--model", default=None,
                        help="Model label e.g. 'GPT-4o (OpenAI)' or 'Claude Sonnet 4.6 (Anthropic)'")
    args = parser.parse_args()

    run_batch(args.dir, verbose=args.verbose, model_label=args.model)
