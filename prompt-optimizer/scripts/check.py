#!/usr/bin/env python3
"""Score prompt outputs against assertions, and diff two prompt versions.

This is the part that makes a claimed improvement checkable. It does not call
any model — you produce outputs, this decides whether they passed.

Files
  spec.json     {"assertions": [...]}          the checks
  outputs.jsonl {"case_id": "...", "output": "..."}   one line per case

Usage
  check.py spec.json outputs.jsonl [--json]
  check.py spec.json baseline.jsonl --compare candidate.jsonl
  check.py spec.json --export-promptfoo > promptfooconfig.yaml
  check.py --selftest

Assertion types
  regex / not_regex        value: pattern
  contains / not_contains  value: substring          (icase: true)
  contains_all / contains_any   value: [substrings]
  word_count / sentence_count   min, max
  is_json                  output must parse as JSON
  json_keys                value: [required top-level keys]
  max_occurrences          value: pattern, max: N    (distinct matches)
  no_repeat_ngram          n: N   GLOBAL — no N-word run shared across outputs
"""
import argparse
import json
import re
import sys
from collections import Counter

GLOBAL_TYPES = {"no_repeat_ngram"}


def _words(s):
    return re.findall(r"[A-Za-z0-9'\-]+", s)


def _sentences(s):
    return [x for x in re.split(r"[.!?]+(?:\s|$)", s.strip()) if x.strip()]


def _flags(a):
    return re.I if a.get("icase") else 0


def run_one(a, out):
    """-> (passed: bool, detail: str)"""
    t = a["type"]
    v = a.get("value")

    if t == "regex":
        return bool(re.search(v, out, _flags(a))), f"no match for /{v}/"
    if t == "not_regex":
        m = re.search(v, out, _flags(a))
        return not m, f"matched /{v}/ at {m.group(0)!r}" if m else ""
    if t == "contains":
        hay, needle = (out.lower(), v.lower()) if a.get("icase") else (out, v)
        return needle in hay, f"missing {v!r}"
    if t == "not_contains":
        hay, needle = (out.lower(), v.lower()) if a.get("icase") else (out, v)
        return needle not in hay, f"contains {v!r}"
    if t == "contains_all":
        missing = [x for x in v if x.lower() not in out.lower()]
        return not missing, f"missing {missing}"
    if t == "contains_any":
        return any(x.lower() in out.lower() for x in v), f"none of {v}"
    if t == "word_count":
        n = len(_words(out))
        lo, hi = a.get("min"), a.get("max")
        ok = (lo is None or n >= lo) and (hi is None or n <= hi)
        return ok, f"{n} words, wanted {lo}-{hi}"
    if t == "sentence_count":
        n = len(_sentences(out))
        lo, hi = a.get("min"), a.get("max")
        ok = (lo is None or n >= lo) and (hi is None or n <= hi)
        return ok, f"{n} sentences, wanted {lo}-{hi}"
    if t == "is_json":
        try:
            json.loads(out)
            return True, ""
        except ValueError as e:
            return False, f"invalid JSON: {e}"
    if t == "json_keys":
        try:
            obj = json.loads(out)
        except ValueError as e:
            return False, f"invalid JSON: {e}"
        if not isinstance(obj, dict):
            return False, f"expected object, got {type(obj).__name__}"
        missing = [k for k in v if k not in obj]
        return not missing, f"missing keys {missing}"
    if t == "max_occurrences":
        hits = {m.group(0).lower() for m in re.finditer(v, out, _flags(a))}
        return len(hits) <= a["max"], f"{len(hits)} distinct ({sorted(hits)}), max {a['max']}"
    raise ValueError(f"unknown assertion type: {t}")


def run_global(a, outputs):
    """-> (passed, detail). outputs is the full list of output strings."""
    if a["type"] == "no_repeat_ngram":
        n = a.get("n", 4)
        seen, dupes = {}, []
        for idx, out in enumerate(outputs):
            w = [x.lower() for x in _words(out)]
            for g in {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}:
                if g in seen and seen[g] != idx:
                    dupes.append(" ".join(g))
                seen.setdefault(g, idx)
        uniq = sorted(set(dupes))
        return not uniq, f"{len(uniq)} repeated {n}-grams, e.g. {uniq[:3]}"
    raise ValueError(f"unknown global assertion: {a['type']}")


def score(spec, records):
    """-> report dict."""
    asserts = spec["assertions"]
    outputs = [r["output"] for r in records]
    results = []

    for a in asserts:
        aid = a.get("id", a["type"])
        if a["type"] in GLOBAL_TYPES:
            ok, detail = run_global(a, outputs)
            results.append({"id": aid, "scope": "global", "passed": int(ok),
                            "total": 1, "failures": [] if ok else [{"case": "*", "why": detail}]})
            continue
        failures = []
        for r in records:
            ok, detail = run_one(a, r["output"])
            if not ok:
                failures.append({"case": r.get("case_id", "?"), "why": detail})
        results.append({"id": aid, "scope": "case",
                        "passed": len(records) - len(failures),
                        "total": len(records), "failures": failures})

    total = sum(r["total"] for r in results)
    passed = sum(r["passed"] for r in results)
    return {
        "cases": len(records),
        "assertions": len(asserts),
        "checks_passed": passed,
        "checks_total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "per_assertion": results,
    }


def compare(spec, base_recs, cand_recs):
    b, c = score(spec, base_recs), score(spec, cand_recs)
    bmap = {r["id"]: r for r in b["per_assertion"]}
    deltas, regressed, improved = [], [], []
    for r in c["per_assertion"]:
        br = bmap.get(r["id"])
        if not br:
            continue
        b_rate = br["passed"] / br["total"] if br["total"] else 0
        c_rate = r["passed"] / r["total"] if r["total"] else 0
        d = round(c_rate - b_rate, 4)
        deltas.append({"id": r["id"], "baseline": round(b_rate, 4),
                       "candidate": round(c_rate, 4), "delta": d})
        if d < 0:
            regressed.append(r["id"])
        elif d > 0:
            improved.append(r["id"])
    overall = round(c["pass_rate"] - b["pass_rate"], 4)
    if regressed and improved:
        verdict = "MIXED — some checks regressed; decide per assertion"
    elif regressed:
        verdict = "REGRESSED — do not ship"
    elif improved:
        verdict = "IMPROVED"
    else:
        verdict = "NO CHANGE — the rewrite did not move any measured check"
    return {"baseline_pass_rate": b["pass_rate"], "candidate_pass_rate": c["pass_rate"],
            "overall_delta": overall, "verdict": verdict, "improved": improved,
            "regressed": regressed, "per_assertion": deltas}


# --- promptfoo export ------------------------------------------------------

_PF = {"regex": "regex", "not_regex": "not-regex", "contains": "contains",
       "not_contains": "not-contains", "contains_all": "contains-all",
       "contains_any": "contains-any", "is_json": "is-json"}


def export_promptfoo(spec):
    lines = ["# generated by prompt-optimizer/scripts/check.py",
             "prompts:", "  - file://prompt.txt", "providers:",
             "  - anthropic:messages:claude-sonnet-5", "defaultTest:", "  assert:"]
    # Counting expressions mirror _words() and _sentences() so promptfoo and
    # check.py agree on the same output.
    _JS_COUNT = {
        "word_count": "(output.match(/[A-Za-z0-9'-]+/g)||[]).length",
        "sentence_count": "output.trim().split(/[.!?]+(?:\\s|$)/).filter(s=>s.trim()).length",
    }
    skipped = []
    for a in spec["assertions"]:
        t = a["type"]
        if t in _PF:
            lines.append(f"    - type: {_PF[t]}")
            if a.get("value") is not None:
                lines.append(f"      value: {json.dumps(a['value'])}")
        elif t in _JS_COUNT:
            expr = _JS_COUNT[t]
            lo, hi = a.get("min"), a.get("max")
            bounds = []
            if lo is not None:
                bounds.append(f"{expr} >= {lo}")
            if hi is not None:
                bounds.append(f"{expr} <= {hi}")
            lines.append("    - type: javascript")
            lines.append(f"      value: {' && '.join(bounds) or 'true'}")
        else:
            skipped.append(a.get("id", t))
    if skipped:
        lines.append(f"# not exportable, run via check.py: {', '.join(skipped)}")
    return "\n".join(lines) + "\n"


# --- io --------------------------------------------------------------------

def load_jsonl(path):
    recs = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError as e:
                raise SystemExit(f"{path}:{n}: invalid JSON — {e}")
            if "output" not in obj:
                raise SystemExit(f"{path}:{n}: record has no 'output' field")
            recs.append(obj)
    if not recs:
        raise SystemExit(f"{path}: no records")
    return recs


def render_score(rep):
    out = [f"{rep['cases']} cases · {rep['assertions']} assertions · "
           f"{rep['checks_passed']}/{rep['checks_total']} checks passed "
           f"({rep['pass_rate']:.0%})", ""]
    for r in sorted(rep["per_assertion"], key=lambda x: x["passed"] / max(x["total"], 1)):
        mark = "PASS" if r["passed"] == r["total"] else "FAIL"
        out.append(f"[{mark}] {r['id']}  {r['passed']}/{r['total']}")
        for f in r["failures"][:5]:
            out.append(f"         {f['case']}: {f['why']}")
        if len(r["failures"]) > 5:
            out.append(f"         ... {len(r['failures']) - 5} more")
    return "\n".join(out)


def render_compare(rep):
    out = [rep["verdict"],
           f"baseline {rep['baseline_pass_rate']:.0%} → candidate "
           f"{rep['candidate_pass_rate']:.0%}  ({rep['overall_delta']:+.1%})", ""]
    for d in sorted(rep["per_assertion"], key=lambda x: x["delta"]):
        arrow = "▼" if d["delta"] < 0 else ("▲" if d["delta"] > 0 else " ")
        out.append(f" {arrow} {d['id']:<32} {d['baseline']:.0%} → {d['candidate']:.0%}"
                   f"  ({d['delta']:+.0%})")
    return "\n".join(out)


# --- selftest --------------------------------------------------------------

def selftest():
    spec = {"assertions": [
        {"id": "no-instance-types", "type": "not_regex", "value": r"\b[a-z]\d[a-z]*\.\w+\b"},
        {"id": "length", "type": "word_count", "min": 5, "max": 12},
        {"id": "svc-cap", "type": "max_occurrences", "value": r"\b(EC2|RDS|S3|Lambda)\b", "max": 2},
        {"id": "variety", "type": "no_repeat_ngram", "n": 4},
    ]}
    recs = [
        {"case_id": "a", "output": "Aurora holds the records for the retail team here"},
        {"case_id": "b", "output": "runs on a db.r5.xlarge node"},
        {"case_id": "c", "output": "EC2 and RDS and S3 all serve this workload today"},
    ]
    rep = score(spec, recs)
    per = {r["id"]: r for r in rep["per_assertion"]}

    assert per["no-instance-types"]["passed"] == 2, "b leaks db.r5.xlarge"
    assert per["no-instance-types"]["failures"][0]["case"] == "b"
    assert per["length"]["passed"] == 3, "a=9, b=7, c=10 words — all within 5-12"
    assert per["svc-cap"]["passed"] == 2, "c names 3 services"
    assert per["variety"]["total"] == 1 and per["variety"]["scope"] == "global"

    # word_count boundary: exactly at min and max both pass.
    assert run_one({"type": "word_count", "min": 3, "max": 3}, "one two three")[0]
    assert not run_one({"type": "word_count", "min": 4, "max": 9}, "one two three")[0]

    # max_occurrences counts DISTINCT matches, so repetition doesn't trip the cap.
    ok, _ = run_one({"type": "max_occurrences", "value": r"\bEC2\b", "max": 1}, "EC2 EC2 EC2")
    assert ok, "same service named 3x is still 1 distinct service"

    # is_json / json_keys
    assert run_one({"type": "is_json"}, '{"a":1}')[0]
    assert not run_one({"type": "is_json"}, "nope")[0]
    assert not run_one({"type": "json_keys", "value": ["a", "b"]}, '{"a":1}')[0]

    # no_repeat_ngram fires on a shared 4-word run, not on distinct text.
    dup = [{"output": "the quick brown fox jumps"}, {"output": "the quick brown fox sleeps"}]
    assert not run_global({"type": "no_repeat_ngram", "n": 4}, [d["output"] for d in dup])[0]
    uniq = [{"output": "alpha beta gamma delta"}, {"output": "one two three four"}]
    assert run_global({"type": "no_repeat_ngram", "n": 4}, [u["output"] for u in uniq])[0]

    # A strictly worse candidate must read as REGRESSED.
    worse = [{"case_id": "a", "output": "runs on m5.large with EC2 and RDS and S3 here"}] * 3
    cmp = compare(spec, recs, worse)
    assert cmp["verdict"].startswith("REGRESSED"), cmp["verdict"]
    assert "no-instance-types" in cmp["regressed"]

    # Goodhart guard: emitting LESS content can pass a cap check while the output
    # gets worse. That must surface as MIXED, never as a clean win.
    sparse = [{"case_id": "a", "output": "runs on m5.large here now ok"}] * 3
    mixed = compare(spec, recs, sparse)
    assert mixed["verdict"].startswith("MIXED"), mixed["verdict"]
    assert "svc-cap" in mixed["improved"] and "no-instance-types" in mixed["regressed"]

    same = compare(spec, recs, recs)
    assert same["verdict"].startswith("NO CHANGE"), same["verdict"]

    # promptfoo export: convertible types emitted, the rest named in a comment.
    yaml = export_promptfoo(spec)
    assert "not-regex" in yaml
    assert "svc-cap" in yaml and "variety" in yaml, "unconvertible types must be listed"
    sc = export_promptfoo({"assertions": [{"type": "sentence_count", "min": 2, "max": 4}]})
    assert "type: javascript" in sc and ">= 2" in sc and "<= 4" in sc
    print("selftest ok")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec", nargs="?")
    p.add_argument("outputs", nargs="?")
    p.add_argument("--compare", metavar="CANDIDATE.jsonl")
    p.add_argument("--export-promptfoo", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()

    if a.selftest:
        selftest()
        return 0
    if not a.spec:
        p.error("spec required (or --selftest)")
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)

    if a.export_promptfoo:
        sys.stdout.write(export_promptfoo(spec))
        return 0
    if not a.outputs:
        p.error("outputs.jsonl required")

    base = load_jsonl(a.outputs)
    if a.compare:
        rep = compare(spec, base, load_jsonl(a.compare))
        print(json.dumps(rep, indent=2) if a.json else render_compare(rep))
        return 1 if rep["regressed"] else 0
    rep = score(spec, base)
    print(json.dumps(rep, indent=2) if a.json else render_score(rep))
    return 1 if rep["checks_passed"] < rep["checks_total"] else 0


if __name__ == "__main__":
    sys.exit(main())
