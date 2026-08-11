#!/usr/bin/env python3
"""Static defect scanner for LLM prompts. Stdlib only, no API calls.

Finds the defects that are mechanically detectable: constraints that contradict
each other, examples that violate the prompt's own stated limits, deprecated
API patterns, unbalanced tags, duplicated rules.

Usage:
  lint.py PROMPT_FILE [--json]
  lint.py --selftest
"""
import argparse
import json
import re
import sys
from collections import defaultdict

# --- constraint extraction -------------------------------------------------

_RANGE = re.compile(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)\s+(\w+)", re.I)
_MAX = re.compile(
    r"(?:max(?:imum)?(?:\s+of)?|at most|no more than|not exceed|under|up to|"
    r"fewer than|less than|≤|<=)\s*(\d+)\s+(\w+)",
    re.I,
)
_MIN = re.compile(r"(?:min(?:imum)?(?:\s+of)?|at least|no fewer than|≥|>=)\s*(\d+)\s+(\w+)", re.I)

# Units too generic to compare meaningfully.
_NOISE_UNITS = {
    "the", "and", "or", "of", "a", "an", "in", "on", "for", "to", "is", "are",
    "other", "more", "less", "than", "times", "x",
}


def _unit(word):
    w = word.lower()
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _compound(line, end):
    """True if the unit word is the head of a compound ('single-service')."""
    return end < len(line) and line[end] == "-"


def extract_constraints(text):
    """-> {unit: [(lo, hi, line_no, raw), ...]}  hi=None means open-ended."""
    out = defaultdict(list)
    for i, line in enumerate(text.splitlines(), 1):
        for m in _RANGE.finditer(line):
            lo, hi, unit = int(m.group(1)), int(m.group(2)), _unit(m.group(3))
            if unit in _NOISE_UNITS or lo > hi or _compound(line, m.end()):
                continue
            out[unit].append((lo, hi, i, line.strip()[:70]))
        for m in _MAX.finditer(line):
            unit = _unit(m.group(2))
            if unit in _NOISE_UNITS or _compound(line, m.end()):
                continue
            out[unit].append((None, int(m.group(1)), i, line.strip()[:70]))
        for m in _MIN.finditer(line):
            unit = _unit(m.group(2))
            if unit in _NOISE_UNITS or _compound(line, m.end()):
                continue
            out[unit].append((int(m.group(1)), None, i, line.strip()[:70]))
    return out


# --- exemplar extraction ---------------------------------------------------

_EXEMPLAR_LINE = re.compile(
    r"^\s*(?:[>\-*]\s*)?(?:\*\*)?"
    r"(description|output|answer|response|result|summary|completion|assistant)"
    r"(?:\*\*)?\s*[:=]\s*(.+)$",
    re.I,
)
_LONG_QUOTED = re.compile(r'"([^"\n]{80,})"')


def extract_exemplars(text):
    """Lines that look like a demonstrated model output. -> [(line_no, text)]"""
    found = []
    for i, line in enumerate(text.splitlines(), 1):
        m = _EXEMPLAR_LINE.match(line)
        if m:
            body = m.group(2).strip().strip('"').strip()
            if len(body.split()) >= 5:
                found.append((i, body))
                continue
        for q in _LONG_QUOTED.finditer(line):
            body = q.group(1).strip()
            if len(body.split()) >= 15:
                found.append((i, body))
    return found


# --- deprecated / stale patterns ------------------------------------------

DEPRECATED = [
    (r"\bprefill(?:ed|ing)?\b|\bassistant\s+turn\s+prefix\b",
     "Prefilled assistant turns return 400 on Claude 4.6+. Use structured outputs "
     "or an explicit 'respond without preamble' instruction."),
    (r"\bbudget_tokens\b",
     "budget_tokens is rejected on Opus 4.7+. Use adaptive thinking with `effort`."),
    (r"(?:CRITICAL|IMPORTANT|YOU MUST)[^\n]{0,40}\b(?:MUST|ALWAYS)\b[^\n]{0,60}\btool\b",
     "Emphatic tool-use pressure causes overtriggering on Claude 4.x. Plain "
     "'Use this tool when...' performs better."),
    (r"\b\d+\s*(?:-|–|to)\s*\d+\s+words\b|\bword count\b|\bmax(?:imum)? \d+ words\b",
     "Word-count limits bind poorly (tokenization). Specify sentence or paragraph "
     "counts instead."),
    (r"\btake a deep breath\b|\byou are a world[- ]class\b|\bI will tip you\b",
     "Folk-prompting incantation with no measured effect on current models. Drop it."),
]

# --- checks ----------------------------------------------------------------


def _f(sev, code, msg, line=None):
    return {"severity": sev, "code": code, "message": msg, "line": line}


def check_constraint_conflicts(text):
    out = []
    for unit, items in extract_constraints(text).items():
        if len(items) < 2:
            continue
        distinct = {(lo, hi) for lo, hi, _, _ in items}
        if len(distinct) < 2:
            continue
        seen, where = set(), []
        for _, _, ln, ctx in items:
            if ctx not in seen:
                seen.add(ctx)
                where.append(f"    L{ln}: {ctx}")
        out.append(_f("high", "constraint-conflict",
                      f"{len(distinct)} different limits stated for '{unit}':\n"
                      + "\n".join(where)
                      + "\n    Confirm these govern the same field. If they do, the model "
                        "cannot satisfy all of them — pick one.",
                      items[0][2]))
    return out


def check_exemplars_vs_constraints(text):
    """Do the prompt's own examples obey its stated word limits?"""
    out = []
    cons = extract_constraints(text).get("word", [])
    if not cons:
        return out
    los = [lo for lo, _, _, _ in cons if lo is not None]
    his = [hi for _, hi, _, _ in cons if hi is not None]
    lo = max(los) if los else None
    hi = max(his) if his else None
    for line_no, body in extract_exemplars(text):
        n = len(body.split())
        if lo is not None and n < lo:
            out.append(_f("high", "example-violates-constraint",
                          f"Example is {n} words but the prompt states a {lo}-word floor. "
                          f"Models copy examples over instructions — the effective floor "
                          f"is {n}.", line_no))
        elif hi is not None and n > hi:
            out.append(_f("high", "example-violates-constraint",
                          f"Example is {n} words, over the stated {hi}-word ceiling.",
                          line_no))
    return out


_NEVER = re.compile(r"\b(?:never|forbidden|do not|don't|must not|prohibited|banned)\b", re.I)
_ALLOW = re.compile(r"\b(?:allowed|acceptable|is fine|is ok|may appear|permitted|encouraged)\b", re.I)
_TERM = re.compile(r'"([^"\n]{2,40})"|\*\*([^*\n]{2,40})\*\*|`([^`\n]{2,40})`')


def _terms(line):
    return {
        (a or b or c).strip().lower()
        for a, b, c in _TERM.findall(line)
        if len((a or b or c).strip()) > 1
    }


def check_allow_forbid_collision(text):
    forbid, allow = defaultdict(list), defaultdict(list)
    for i, line in enumerate(text.splitlines(), 1):
        # Both on one line is a scoped exception ("never X, except when Y"),
        # not a contradiction. Only cross-line pairs are suspicious.
        neg, pos = bool(_NEVER.search(line)), bool(_ALLOW.search(line))
        if neg == pos:  # both (scoped exception) or neither
            continue
        bucket = forbid if neg else allow
        for t in _terms(line):
            bucket[t].append(i)
    out = []
    for term in sorted(set(forbid) & set(allow)):
        out.append(_f("medium", "allow-forbid-collision",
                      f"'{term}' is forbidden on L{forbid[term][0]} but allowed on "
                      f"L{allow[term][0]}. State the exception inline with the rule.",
                      forbid[term][0]))
    return out


def check_deprecated(text):
    out = []
    for pat, msg in DEPRECATED:
        rx = re.compile(pat, re.I)
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                out.append(_f("medium", "stale-pattern", msg, i))
                break
    return out


_TAG = re.compile(r"</?([a-zA-Z][\w:-]*)\s*/?>")
_QUOTED_SPAN = re.compile(r"`[^`\n]*`|\"[^\"\n]*\"")


def check_tag_balance(text):
    # `<id>` and "<Customer>" are placeholders, not markup. Drop quoted spans,
    # and treat a Capitalized tag name as a placeholder too.
    stripped = _QUOTED_SPAN.sub(" ", text)
    counts = defaultdict(lambda: [0, 0])
    for m in _TAG.finditer(stripped):
        name = m.group(1)
        if m.group(0).endswith("/>") or name[0].isupper():
            continue
        counts[name][0 if not m.group(0).startswith("</") else 1] += 1
    out = []
    for tag, (op, cl) in sorted(counts.items()):
        if op != cl:
            out.append(_f("low", "unbalanced-tag",
                          f"<{tag}> opened {op}x, closed {cl}x."))
    return out


def check_duplicate_rules(text):
    seen = defaultdict(list)
    for i, line in enumerate(text.splitlines(), 1):
        norm = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        if len(norm.split()) >= 6:
            seen[norm].append(i)
    return [
        _f("low", "duplicate-rule",
           f"Identical instruction on lines {lines}. Restating a rule adds tokens "
           f"and lets the copies drift apart.", lines[0])
        for norm, lines in seen.items() if len(lines) > 1
    ]


def check_output_contract(text):
    low = text.lower()
    has_format = any(k in low for k in (
        "output format", "respond with", "return only", "json", "<output", "format:",
        "response format", "schema"))
    if not has_format:
        return [_f("medium", "no-output-contract",
                   "No output format is specified. Unspecified format is the most "
                   "common source of 'inconsistent' output.")]
    return []


def check_negation_balance(text):
    neg = len(_NEVER.findall(text))
    if neg >= 15:
        return [_f("low", "negation-heavy",
                   f"{neg} prohibitions found. Models follow 'do X' more reliably than "
                   f"'never do Y' — convert the top offenders to positive form.")]
    return []


CHECKS = [
    check_constraint_conflicts,
    check_exemplars_vs_constraints,
    check_allow_forbid_collision,
    check_deprecated,
    check_tag_balance,
    check_duplicate_rules,
    check_output_contract,
    check_negation_balance,
]

_ORDER = {"high": 0, "medium": 1, "low": 2}


def lint(text):
    findings = []
    for c in CHECKS:
        findings.extend(c(text))
    findings.sort(key=lambda f: (_ORDER[f["severity"]], f["line"] or 0))
    words = len(text.split())
    return {
        "stats": {
            "lines": len(text.splitlines()),
            "words": words,
            "approx_tokens": round(len(text) / 4),
            "exemplars_found": len(extract_exemplars(text)),
        },
        "findings": findings,
    }


def render(report):
    s = report["stats"]
    lines = [
        f"{s['lines']} lines · {s['words']} words · ~{s['approx_tokens']} tokens · "
        f"{s['exemplars_found']} examples detected",
        "",
    ]
    if not report["findings"]:
        lines.append("No mechanical defects found. Run the LLM-judged audit for the rest.")
    for f in report["findings"]:
        loc = f"L{f['line']}" if f["line"] else "—"
        lines.append(f"[{f['severity'].upper():6}] {loc:>6}  {f['code']}")
        lines.append(f"                 {f['message']}")
    return "\n".join(lines)


# --- selftest --------------------------------------------------------------

_FIXTURE = '''
# Task
Write a summary.

Length: 35-70 words at MAX. Prefer 35-55 for simple cases.
Output must be 30-70 words.

"cluster" is allowed when literal.
Never use the word "cluster" as the primary noun.

## Example
Description: "A short one that is far too brief to pass the floor at all."

<thinking>
reason here
'''


def selftest():
    r = lint(_FIXTURE)
    codes = [f["code"] for f in r["findings"]]

    assert "constraint-conflict" in codes, "should catch 35-70 vs 30-70 for 'word'"
    assert "example-violates-constraint" in codes, "13-word example under 35-word floor"
    assert "allow-forbid-collision" in codes, "'cluster' allowed and forbidden"
    assert "unbalanced-tag" in codes, "<thinking> never closed"
    # A length rule is not a format contract.
    assert "no-output-contract" in codes, "fixture never states an output format"

    # Constraint parsing.
    c = extract_constraints("use 5-12 words and at most 3 services and at least 2 regions")
    assert (5, 12) in {(lo, hi) for lo, hi, _, _ in c["word"]}
    assert (None, 3) in {(lo, hi) for lo, hi, _, _ in c["service"]}
    assert (2, None) in {(lo, hi) for lo, hi, _, _ in c["region"]}

    # No false positive when the prompt is consistent.
    clean = 'Write 30-50 words.\nOutput format: plain text.\nDescription: "' + \
            " ".join(["word"] * 40) + '"'
    clean_codes = [f["code"] for f in lint(clean)["findings"]]
    assert "constraint-conflict" not in clean_codes
    assert "example-violates-constraint" not in clean_codes
    assert "no-output-contract" not in clean_codes, "clean fixture declares a format"

    # Unit normalization.
    assert _unit("Services") == "service"
    assert _unit("words") == "word"
    assert _unit("class") == "class"

    print("selftest ok")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prompt_file", nargs="?")
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()

    if a.selftest:
        selftest()
        return 0
    if not a.prompt_file:
        p.error("prompt_file required (or --selftest)")

    with open(a.prompt_file, encoding="utf-8") as fh:
        report = lint(fh.read())
    print(json.dumps(report, indent=2) if a.json else render(report))
    return 1 if any(f["severity"] == "high" for f in report["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
