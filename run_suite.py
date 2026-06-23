#!/usr/bin/env python3
"""
Prompt regression suite runner.

Loads a prompt, runs every test case through the model, applies deterministic
and judged scorers, and prints a per-case + aggregate report. Can compare
against a committed baseline and exit non-zero on regression (for CI).

Usage:
    python run_suite.py --mock                  # no API key needed
    python run_suite.py                          # real model + judge
    python run_suite.py --mock --check-baseline  # fail if scores regress

Mock mode produces stable pseudo-scores so the pipeline is fully runnable
without any API key — useful for local dev and for CI demos.
"""

import argparse
import hashlib
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scoring.deterministic import DETERMINISTIC_CHECKS
from scoring.judge import JUDGED_ASSERTIONS, judge_binary, judge_quality

ROOT = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(ROOT, "prompts", "draft_reply.txt")
CASES_PATH = os.path.join(ROOT, "tests", "cases.yaml")
BASELINE_PATH = os.path.join(ROOT, "baseline.json")

# A case's score may drop by at most this much vs baseline before it's a regression.
REGRESSION_TOLERANCE = 0.0


def load_prompt():
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def load_cases():
    with open(CASES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_prompt(template, case):
    ctx = case["input"]["context"]
    return template.format(
        message=case["input"]["message"],
        customer_name=ctx.get("customer_name") or "(not provided)",
        order_id=ctx.get("order_id") or "(not provided)",
        product=ctx.get("product") or "(not provided)",
    )


def generate_reply(filled_prompt, case, mock):
    """Get the drafted reply from the model (or a mock stand-in)."""
    if mock:
        # Deterministic stand-in reply so the pipeline runs end-to-end offline.
        name = case["input"]["context"].get("customer_name") or "there"
        oid = case["input"]["context"].get("order_id") or ""
        ref = f" regarding order {oid}" if oid else ""
        return (
            f"Hi {name},\n\n"
            f"Thank you for reaching out{ref}. I understand your concern and "
            f"I'm here to help. Here's what we can do next: I'll look into this "
            f"and follow up with the details.\n\n"
            f"Best regards,\nThe Support Team"
        )
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": filled_prompt}],
    )
    return resp.content[0].text.strip()


def score_case(reply, case, mock):
    """Return a per-case result dict with assertion outcomes and a 0-1 score."""
    results = {"must_contain": {}, "must_not": {}, "qualities": {}}
    passed = 0
    total = 0

    # must_contain: property should HOLD
    for item in case["assert"].get("must_contain", []):
        t = item["type"]
        if t in DETERMINISTIC_CHECKS:
            holds = DETERMINISTIC_CHECKS[t](reply, case)
        else:
            holds = judge_binary(t, reply, case, mock=mock)
        results["must_contain"][t] = holds
        passed += 1 if holds else 0
        total += 1

    # must_not: property should NOT hold
    for item in case["assert"].get("must_not", []):
        t = item["type"]
        if t in DETERMINISTIC_CHECKS:
            present = DETERMINISTIC_CHECKS[t](reply, case)
        else:
            present = judge_binary(t, reply, case, mock=mock)
        ok = not present
        results["must_not"][t] = ok
        passed += 1 if ok else 0
        total += 1

    # judged qualities: 1-5 vs min_score
    for q in case["assert"].get("judged_qualities", []):
        score = judge_quality(q, reply, case, mock=mock)
        meets = score >= q["min_score"]
        results["qualities"][q["name"]] = {
            "score": score,
            "min_score": q["min_score"],
            "meets": meets,
        }
        passed += 1 if meets else 0
        total += 1

    results["score"] = round(passed / total, 3) if total else 0.0
    results["passed"] = passed
    results["total"] = total
    return results


def run(mock):
    template = load_prompt()
    cases = load_cases()
    prompt_hash = hashlib.sha256(template.encode()).hexdigest()[:8]

    report = {"prompt_hash": prompt_hash, "mock": mock, "cases": {}}
    for case in cases:
        filled = render_prompt(template, case)
        reply = generate_reply(filled, case, mock)
        report["cases"][case["id"]] = score_case(reply, case, mock)

    scores = [c["score"] for c in report["cases"].values()]
    report["aggregate"] = round(sum(scores) / len(scores), 3) if scores else 0.0
    return report


def print_report(report):
    print(f"\nPrompt hash: {report['prompt_hash']}  (mock={report['mock']})")
    print("-" * 60)
    for cid, r in report["cases"].items():
        flag = "PASS" if r["score"] == 1.0 else "----"
        print(f"[{flag}] {cid:28s} {r['passed']}/{r['total']}  score={r['score']}")
    print("-" * 60)
    print(f"Aggregate: {report['aggregate']}\n")


def check_baseline(report):
    if not os.path.exists(BASELINE_PATH):
        print("No baseline.json found. Run with --write-baseline to create one.")
        return 0
    with open(BASELINE_PATH, encoding="utf-8") as f:
        baseline = json.load(f)

    regressions = []
    for cid, r in report["cases"].items():
        base = baseline["cases"].get(cid)
        if base is None:
            continue
        if r["score"] < base["score"] - REGRESSION_TOLERANCE:
            regressions.append((cid, base["score"], r["score"]))

    if regressions:
        print("REGRESSIONS DETECTED:")
        for cid, was, now in regressions:
            print(f"  {cid}: {was} -> {now}")
        return 1
    print("No regressions against baseline.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="run without API calls")
    ap.add_argument("--check-baseline", action="store_true", help="fail on regression")
    ap.add_argument("--write-baseline", action="store_true", help="save current as baseline")
    args = ap.parse_args()

    report = run(mock=args.mock)
    print_report(report)

    if args.write_baseline:
        with open(BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote baseline to {BASELINE_PATH}")
        return

    if args.check_baseline:
        sys.exit(check_baseline(report))


if __name__ == "__main__":
    main()
