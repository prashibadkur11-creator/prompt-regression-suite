"""
LLM-as-judge checks: for assertions that need judgment, not pattern matching.

Two kinds:
  - Binary judged assertions (e.g. acknowledges_frustration, invents_facts):
    the judge returns yes/no.
  - Scored qualities (e.g. empathetic_tone): the judge returns a 1-5 score
    against the case's criteria, compared to min_score.

Supports --mock mode so the full pipeline runs with no API key (deterministic
pseudo-scores derived from the text), which keeps CI demos and local dev free.
"""

import hashlib
import json
import os

# Binary judged assertion types and the question posed to the judge.
JUDGED_ASSERTIONS = {
    "acknowledges_frustration": "Does the reply sincerely acknowledge the customer's frustration?",
    "provides_clear_steps": "Does the reply give clear, followable steps?",
    "invents_facts": "Does the reply state any order detail, date, tracking number, price, or prior conversation NOT present in the message or context?",
    "offers_resolution": "Does the reply offer a concrete resolution or path forward?",
    "dismisses_request": "Does the reply dismiss or brush off the customer's request?",
    "asks_for_clarification": "Does the reply ask a focused clarifying question?",
    "assumes_specific_problem": "Does the reply assume a specific problem that was never stated?",
    "addresses_both_issues": "Does the reply address BOTH issues the customer raised?",
    "addresses_core_question": "Does the reply address the customer's core question directly?",
    "explains_politely": "Does the reply explain politely what can and cannot be done?",
    "rude_or_defensive": "Is the reply rude, defensive, or accusatory?",
    "over_apologizes": "Does the reply apologize repeatedly or grovel (more than once)?",
    "generic_non_answer": "Is the reply a generic non-answer that fails to engage the specifics?",
    "fabricates_prior_context": "Does the reply fabricate details of a prior conversation that were not provided?",
}


def _mock_score(text, salt, low=1, high=5):
    """Deterministic pseudo-score from text hash, stable across runs."""
    h = int(hashlib.sha256((salt + text).encode()).hexdigest(), 16)
    return low + (h % (high - low + 1))


def _mock_bool(text, salt):
    return _mock_score(text, salt, 0, 1) == 1


def _call_judge(prompt):
    """Real judge call. Lazy import so mock mode needs no anthropic package."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def judge_binary(assertion_type, reply, case, mock=False):
    """Returns True if the judged property HOLDS for the reply."""
    question = JUDGED_ASSERTIONS[assertion_type]
    if mock:
        return _mock_bool(reply, assertion_type)
    prompt = (
        f"You are evaluating a customer support reply.\n\n"
        f"Customer message: {case['input']['message']}\n"
        f"Context: {json.dumps(case['input']['context'])}\n\n"
        f"Reply:\n{reply}\n\n"
        f"Question: {question}\n"
        f"Answer with exactly one word: YES or NO."
    )
    return _call_judge(prompt).upper().startswith("YES")


def judge_quality(quality, reply, case, mock=False):
    """Returns an integer 1-5 score for a judged quality."""
    if mock:
        return _mock_score(reply, quality["name"])
    prompt = (
        f"You are scoring a customer support reply on one quality.\n\n"
        f"Customer message: {case['input']['message']}\n"
        f"Context: {json.dumps(case['input']['context'])}\n\n"
        f"Reply:\n{reply}\n\n"
        f"Quality: {quality['name']}\n"
        f"Criteria: {quality['criteria']}\n\n"
        f"Score from 1 (poor) to 5 (excellent). Respond with only the number."
    )
    raw = _call_judge(prompt)
    digits = "".join(c for c in raw if c.isdigit())
    return int(digits[0]) if digits else 1
