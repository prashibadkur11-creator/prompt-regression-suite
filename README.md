# Prompt Regression Suite
![License: MIT](https://img.shields.io/github/license/prashibadkur11-creator/prompt-regression-suite) ![CI](https://img.shields.io/github/actions/workflow/status/prashibadkur11-creator/prompt-regression-suite/prompt-ci.yml?branch=main&label=CI)

This repo applies CI discipline to prompts. Every prompt is a versioned file, every
change goes through a pull request, and CI runs the changed prompt against a fixed test
set, scores the outputs, and fails the check if quality regresses against a committed
baseline.

Changing a prompt changes user-facing behavior as much as changing code does. Prompts
are usually edited casually, with no test of whether quality improved and no protection
against silent regressions ("we made refusals politer and accidentally broke the JSON
output").

[TODO: why customer support, why 15 cases, what I was trying to catch]

## Demo product

A **customer support reply drafter**: given a customer message and some context (name,
order ID, product), it drafts a support reply. The product is intentionally
regression-prone (softening tone can break format; loosening refund language can break
policy), so the test suite has real work to do.

## How it works

```
incoming case ──> prompts/draft_reply.txt ──> model ──> drafted reply ──> scorers ──> score
                                                                              │
                                          deterministic.py + judge.py ────────┘
```

1. `run_suite.py` loads the prompt and fills in each test case's input.
2. It calls the model to draft a reply (or uses a stand-in reply in `--mock` mode).
3. Each reply is scored against the case's assertions.
4. Scores are compared to `baseline.json`; a drop is a regression.

## Test cases

`tests/cases.yaml` holds 15 cases covering happy path, emotional range, edge cases, and
deliberate regression traps. Each case asserts properties of a good reply rather than an
exact string (LLM output varies, so we test qualities, not literal text):

```yaml
- id: angry-late-delivery
  input:
    message: "This is ridiculous. My order was supposed to arrive Monday..."
    context: { customer_name: "Jordan", order_id: "A-4471", product: "standard shipping order" }
  assert:
    must_contain:
      - type: acknowledges_frustration
      - type: includes_sign_off
    must_not:
      - type: promises_refund
      - type: invents_facts
    judged_qualities:
      - name: empathetic_tone
        criteria: "Acknowledges frustration without being defensive"
        min_score: 4
```

Each assertion's `type` maps to a checker that is either:

- **deterministic** (`scoring/deterministic.py`). Exact pattern checks like `includes_sign_off`
  or `promises_refund`. Cheap, never flaky, no model calls.
- **judged** (`scoring/judge.py`). LLM-as-judge checks for things you can't regex, like
  `acknowledges_frustration` or the 1–5 quality scores.

Use deterministic checks wherever possible. Spend judge calls only where judgment is
genuinely needed.

`refund-eligible-polite` covers a damaged item where a refund is allowed.
`refund-bait-not-eligible` covers a change of mind where it is not.

## Running it

```bash
pip install -r requirements.txt

# Full pipeline, no API key needed (stand-in replies + stable pseudo-scores)
python run_suite.py --mock

# Real model + judge (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-...
python run_suite.py

# Fail on regression vs baseline (what CI runs)
python run_suite.py --mock --check-baseline

# Accept current scores as the new baseline
python run_suite.py --write-baseline
```

`--mock` mode runs the entire pipeline offline, so CI works on every PR for free and you
can develop without spending tokens. Swap to the real model for meaningful scores.

## The PR workflow

This repo is meant to be worked through pull requests:

1. Create a branch and edit `prompts/draft_reply.txt`.
2. Open a PR. The **Prompt CI** action runs the suite against the baseline.
3. If a case regresses, the check fails and the prompt change is blocked until fixed.
4. If you intentionally accept a new quality level, update `baseline.json` in the same PR
   so the change is visible in the diff.

## Plugging in your own product

1. Replace `prompts/draft_reply.txt` with your prompt (use `{placeholders}` for inputs).
2. Rewrite `tests/cases.yaml` with your inputs and assertions.
3. Add any new deterministic checks to `scoring/deterministic.py` and judged assertion
   types to `scoring/judge.py`.
4. Add `ANTHROPIC_API_KEY` as a GitHub repo secret if you want CI to score against the
   real model (Settings → Secrets and variables → Actions), and drop `--mock` from the
   workflow.
5. Run `python run_suite.py --write-baseline` once on `main` to set your baseline.

## Repo layout

```
.
├── prompts/draft_reply.txt        # the prompt under version control
├── tests/cases.yaml               # 15 test cases (inputs + assertions)
├── scoring/
│   ├── deterministic.py           # exact/pattern checks
│   └── judge.py                   # LLM-as-judge checks (+ mock mode)
├── run_suite.py                   # orchestrator + baseline comparison
├── baseline.json                  # committed baseline scores
└── .github/workflows/prompt-ci.yml  # the PR gate
```

## Limitations

[TODO: --mock pseudo-scores validate the pipeline, not prompt quality]

[TODO: judge score variance run-to-run, and how min_score: 4 was chosen]

[TODO: 15 cases is demo-sized — what a real set would need]

[TODO: baseline.json can be edited down in the same PR; deliberate trade-off]

## License

MIT.
