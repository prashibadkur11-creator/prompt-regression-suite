"""
Deterministic checks: cheap, exact, never flaky. No model calls.

Each function takes (reply_text, case) and returns True if the assertion HOLDS.
For must_contain types, True means the desired property is present.
For must_not types, True means the forbidden property is present (i.e. a violation).
The runner interprets the result based on which section the assertion came from.
"""

import re

REFUND_PATTERNS = [
    r"\brefund(ed|ing)?\b",
    r"\bmoney back\b",
    r"\breimburse",
    r"\bfull refund\b",
]

SIGN_OFF_PATTERNS = [
    r"\b(best|kind|warm)\s+regards\b",
    r"\bsincerely\b",
    r"\bthanks?\b[\s,]*\n",
    r"\bthe support team\b",
    r"\bcustomer (support|care) team\b",
    r"\bbest\b[\s,]*\n",
]

SLANG_PATTERNS = [
    r"\blmao\b", r"\blol\b", r"\byo\b", r"\bbusted\b",
    r"\bstraight up\b", r"\bgonna\b", r"\bwanna\b", r"\bsup\b",
]


def includes_sign_off(reply, case):
    text = reply.strip().lower()
    return any(re.search(p, text) for p in SIGN_OFF_PATTERNS)


def references_order_id(reply, case):
    order_id = (case["input"]["context"].get("order_id") or "").strip()
    if not order_id:
        return False
    return order_id.lower() in reply.lower()


def promises_refund(reply, case):
    """Returns True if refund language is present (a violation for must_not)."""
    text = reply.lower()
    return any(re.search(p, text) for p in REFUND_PATTERNS)


def mirrors_slang(reply, case):
    """Returns True if the reply echoes slang (a violation for must_not)."""
    text = reply.lower()
    return any(re.search(p, text) for p in SLANG_PATTERNS)


# Registry: assertion type -> checker function
DETERMINISTIC_CHECKS = {
    "includes_sign_off": includes_sign_off,
    "references_order_id": references_order_id,
    "promises_refund": promises_refund,
    "mirrors_slang": mirrors_slang,
}
