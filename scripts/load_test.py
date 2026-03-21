"""
TRUTHFORGE AI — Load Test Script
=================================
Runs the pipeline repeatedly on sample transcripts to measure:
- Runtime per run (seconds)
- Success / failure rate
- Optional: limited concurrency (5 parallel runs)

Results saved to:
    artifacts/load_test_results.csv   ← per-run data
    reports/load_test_results.md      ← formatted summary report

Usage:
    cd /path/to/truthforge
    python scripts/load_test.py                    # 10 sequential runs, no LLM
    python scripts/load_test.py --runs 20          # 20 sequential runs
    python scripts/load_test.py --concurrent 5     # 5 concurrent runs
    python scripts/load_test.py --use-llm          # use real LLM (requires .env)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev

# --- Add project root to path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- Sample transcripts for load testing ---
SAMPLE_TRANSCRIPTS = [
    # T1: Simple with clear inconsistency
    """
    COURT HEARING — HC/S 1001/2024
    Before: Justice Tan Wei Ming
    Date: 10 January 2024

    PW1 (Ms. Sarah Lim): I saw the defendant at Orchard Road at 8:00pm on 9 January 2024.
    Defence: Where were you standing?
    PW1: I was at the bus stop outside Ion Orchard.

    DW1 (Mr. Ahmad Salleh): The defendant was with me at Changi Airport Terminal 3 from 7:30pm to 10:00pm on 9 January 2024.
    We were collecting my brother who arrived on SQ flight from Hong Kong at 8:15pm.
    """.strip(),

    # T2: No inconsistency
    """
    COURT HEARING — MC/CC 2002/2024
    Before: District Judge Lee Hwee Boon
    Date: 5 February 2024

    PW1 (Mr. Raj Kumar): On 3 February 2024 at about 2:00pm I was at my shop at Tekka Market.
    I heard a loud noise from outside and saw the defendant run past.

    PW2 (Ms. Priya Nair): I was at Tekka Market on 3 February 2024 at about 2:05pm.
    I also saw a man run past. He matched the description of the defendant.

    The CCTV footage from 3 February 2024 at 2:02pm shows a male matching the defendant's description.
    """.strip(),

    # T3: Date mismatch
    """
    COURT HEARING — HC/S 3003/2024
    Before: Justice Chua Beng Hong
    Date: 20 March 2024

    PW1 (Inspector Koh): The incident occurred on 15 March 2024.
    The complainant called police at 11:30pm on 15 March 2024.

    Defence: My client has receipts showing he was at a restaurant in Sentosa on 14 March 2024 at 11:00pm.
    DW1 (Mr. Tan): Yes, I dined with the accused at Coastes Restaurant on 14 March 2024.
    We left at about midnight.

    PW1 (re-examination): I confirm the incident date was 15 March 2024, not 14 March 2024.
    """.strip(),

    # T4: Location conflict
    """
    CRIMINAL CASE — DAC 4004/2024
    Before: District Judge Wong Kah Wai
    Date: 1 April 2024

    Prosecution: On 30 March 2024 at 9:00pm the accused was seen at Bedok North Avenue 3.
    PW2: I clearly identified him at the void deck of Block 512 Bedok North at exactly 9pm.

    Defence: The accused was at Jurong East MRT station at 9:00pm on 30 March 2024.
    DW1: I met him at Jurong East MRT at 8:55pm. We took the train together until 9:30pm.
    """.strip(),

    # T5: Evolving testimony
    """
    COURT HEARING — DC/S 5005/2024
    Before: District Judge Soh Meng Kuan
    Date: 12 April 2024

    PW1 (complainant): On 10 April 2024 the accused came to my office alone.
    Q: Was anyone else present?
    PW1: No, he came alone.

    [Later in cross-examination]
    PW1: Actually, he brought a colleague named Marcus Yeo.
    Q: Why did you not mention Marcus Yeo earlier?
    PW1: I forgot. Marcus Yeo is his business partner and he told me to sign the documents.
    """.strip(),
]


def run_single(
    transcript: str,
    run_num: int,
    use_llm: bool = False,
    llm_config: dict | None = None,
) -> dict:
    """Execute one pipeline run and return timing + result data."""
    from agents.orchestration_agent import run_pipeline
    from core.memory import new_thread_id

    run_id = str(uuid.uuid4())[:8]
    thread_id = new_thread_id()
    transcript_len = len(transcript)

    start = time.perf_counter()
    try:
        result = run_pipeline(
            transcript,
            llm_config=llm_config if use_llm else None,
            thread_id=thread_id,
        )
        duration = time.perf_counter() - start
        blocked = result.get("security_input_blocked", False)
        error = result.get("error_state")
        n_inconsistencies = len(result.get("inconsistencies", []))
        n_entities = len(result.get("entities", []))
        success = error is None and not blocked
        status = "blocked" if blocked else ("error" if error else "success")
        return {
            "run_id": run_id,
            "run_num": run_num,
            "thread_id": thread_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transcript_chars": transcript_len,
            "duration_s": round(duration, 3),
            "status": status,
            "error": str(error) if error else "",
            "n_inconsistencies": n_inconsistencies,
            "n_entities": n_entities,
            "success": success,
        }
    except Exception as exc:
        duration = time.perf_counter() - start
        return {
            "run_id": run_id,
            "run_num": run_num,
            "thread_id": thread_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transcript_chars": transcript_len,
            "duration_s": round(duration, 3),
            "status": "exception",
            "error": str(exc)[:200],
            "n_inconsistencies": 0,
            "n_entities": 0,
            "success": False,
        }


def run_load_test(
    n_runs: int = 10,
    concurrent: int = 1,
    use_llm: bool = False,
    llm_config: dict | None = None,
) -> list[dict]:
    """Run n_runs pipeline executions, optionally with concurrency."""
    transcripts = [
        SAMPLE_TRANSCRIPTS[i % len(SAMPLE_TRANSCRIPTS)]
        for i in range(n_runs)
    ]

    results: list[dict] = []
    mode = f"{'LLM' if use_llm else 'fallback'} | concurrency={concurrent}"
    print(f"\nTRUTHFORGE Load Test — {n_runs} runs | {mode}")
    print("=" * 60)

    if concurrent <= 1:
        for i, transcript in enumerate(transcripts, 1):
            print(f"  Run {i:3d}/{n_runs} ... ", end="", flush=True)
            r = run_single(transcript, i, use_llm=use_llm, llm_config=llm_config)
            print(f"{r['status']:10s}  {r['duration_s']:.3f}s  "
                  f"incons={r['n_inconsistencies']}")
            results.append(r)
    else:
        with ThreadPoolExecutor(max_workers=concurrent) as pool:
            futures = {
                pool.submit(run_single, t, i, use_llm, llm_config): i
                for i, t in enumerate(transcripts, 1)
            }
            completed = 0
            for future in as_completed(futures):
                completed += 1
                r = future.result()
                print(f"  Run {r['run_num']:3d}/{n_runs} (concurrent) "
                      f"{r['status']:10s}  {r['duration_s']:.3f}s")
                results.append(r)

    return sorted(results, key=lambda x: x["run_num"])


def save_results(results: list[dict]) -> tuple[str, str]:
    """Save CSV and Markdown report. Returns (csv_path, md_path)."""
    PROJECT_ROOT = Path(__file__).parent.parent
    artifacts_dir = PROJECT_ROOT / "artifacts"
    reports_dir = PROJECT_ROOT / "reports"
    artifacts_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    # CSV
    csv_path = str(artifacts_dir / "load_test_results.csv")
    fieldnames = [
        "run_id", "run_num", "thread_id", "timestamp",
        "transcript_chars", "duration_s", "status", "error",
        "n_inconsistencies", "n_entities", "success",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Compute stats
    durations = [r["duration_s"] for r in results]
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    blocked = [r for r in results if r["status"] == "blocked"]
    errors = [r for r in results if r["status"] in ("error", "exception")]

    success_rate = len(successes) / len(results) * 100 if results else 0

    # Markdown report
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md_lines = [
        "# TRUTHFORGE AI — Load Test Results",
        "",
        f"**Generated:** {ts}",
        f"**Total Runs:** {len(results)}",
        "",
        "## Summary Statistics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total runs | {len(results)} |",
        f"| Successful | {len(successes)} ({success_rate:.1f}%) |",
        f"| Failed (error) | {len(errors)} |",
        f"| Blocked (security) | {len(blocked)} |",
        f"| Min runtime | {min(durations):.3f}s |",
        f"| Max runtime | {max(durations):.3f}s |",
        f"| Mean runtime | {mean(durations):.3f}s |",
        f"| Median runtime | {median(durations):.3f}s |",
    ]
    if len(durations) > 1:
        md_lines.append(f"| Std deviation | {stdev(durations):.3f}s |")
    md_lines += [
        "",
        "## Per-Run Results",
        "",
        "| Run | Status | Duration (s) | Inconsistencies | Entities | Chars |",
        "|-----|--------|-------------|-----------------|----------|-------|",
    ]
    for r in results:
        md_lines.append(
            f"| {r['run_num']} | {r['status']} | {r['duration_s']:.3f} "
            f"| {r['n_inconsistencies']} | {r['n_entities']} | {r['transcript_chars']} |"
        )

    if errors:
        md_lines += ["", "## Errors", ""]
        for r in errors:
            md_lines.append(f"- Run {r['run_num']}: `{r['error'][:100]}`")

    md_lines += [
        "",
        "---",
        "",
        "*Load test generated by `scripts/load_test.py`.*",
        "*Results reflect pipeline performance in fallback (no-LLM) or LLM mode.*",
    ]

    md_path = str(reports_dir / "load_test_results.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))

    return csv_path, md_path


def main():
    parser = argparse.ArgumentParser(description="TRUTHFORGE AI Load Test")
    parser.add_argument("--runs", type=int, default=10, help="Number of pipeline runs (default: 10)")
    parser.add_argument("--concurrent", type=int, default=1, help="Concurrent runs (default: 1 = sequential)")
    parser.add_argument("--use-llm", action="store_true", help="Use real LLM (requires API keys in .env)")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Model name (default: claude-sonnet-4-6)")
    parser.add_argument("--provider", default="anthropic", help="Model provider (default: anthropic)")
    args = parser.parse_args()

    # Load env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    llm_config = None
    if args.use_llm:
        llm_config = {"configurable": {"model": args.model, "model_provider": args.provider}}
        print(f"Using LLM: {args.model} ({args.provider})")
    else:
        print("Using fallback mode (no LLM — faster, no API cost)")

    results = run_load_test(
        n_runs=args.runs,
        concurrent=args.concurrent,
        use_llm=args.use_llm,
        llm_config=llm_config,
    )

    csv_path, md_path = save_results(results)

    # Print summary
    durations = [r["duration_s"] for r in results]
    successes = sum(1 for r in results if r["success"])
    print("\n" + "=" * 60)
    print(f"RESULTS: {successes}/{len(results)} successful")
    print(f"Runtime: min={min(durations):.3f}s  mean={mean(durations):.3f}s  max={max(durations):.3f}s")
    print(f"\nSaved: {csv_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
