# tiny-eval

> **Evaluation framework for autonomous AI agents.**
> Define benchmark suites, grade agent runs, track regressions, export reports. Zero dependencies.

[![MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)](https://python.org)

---

## The Problem

You deployed an autonomous agent. It ran for 45 minutes. It opened a PR. Now you need to decide: **do you merge it?**

You could code review it manually — but that's 20 minutes you don't have. You could merge and hope — but agents have a bad habit of introducing subtle regressions that only surface in prod.

What you need is an **eval**: a repeatable benchmark that answers the question objectively.

## What tiny-eval Does

`tiny-eval` is a lightweight eval framework for autonomous agent workflows:

1. **Define a benchmark suite** — a named collection of pass/fail criteria
2. **Run it against any agent context** — tool calls, test results, static analysis, anything
3. **Get an objective grade** — score, pass/fail, per-criterion breakdown
4. **Track regressions** — compare against historical runs
5. **Generate reports** — markdown, JSON, or summary

It was built for the autonomous agent workflow — the kind where agents own issues end-to-end and you need objective, automated quality gates.

---

## Quick Start

### Install

```bash
pip install tiny-eval
```

Or just copy the single file:

```bash
curl -O https://raw.githubusercontent.com/hussain-alsaibai/tiny-eval/main/tiny_eval.py
```

### Define a benchmark

```python
from tiny_eval import Criterion, EvalSuite, eval_run

suite = EvalSuite("bug-fix", [
    Criterion("compiles", "Code must compile without errors",
              lambda ctx: ctx.get("compile_error") is None, required=True),
    Criterion("tests_pass", "All tests pass",
              lambda ctx: ctx.get("test_failures", 0) == 0, weight=2.0),
    Criterion("no_secrets", "No secrets in output",
              lambda ctx: ctx.get("secrets_found", 0) == 0),
], pass_threshold=0.75)
```

### Run an eval

```python
context = {
    "compile_error": None,
    "test_failures": 0,
    "secrets_found": 0,
    "regression_count": 0,
}

result = eval_run("bug-fix", agent_name="cursor", run_id="pr-42", context=context)
print(result.summary())
# ✅ PASS | bug-fix | cursor | score=100.0% | 3 criteria | 2.3ms
```

### Batch evaluation

```python
from tiny_eval import get_evaluator, bug_fix_suite

ev = get_evaluator()
ev.register_suite(bug_fix_suite())

results = ev.run_batch(
    suite_name="bug-fix",
    agent_name="devin",
    run_contexts=[ctx1, ctx2, ctx3],
)

for r in results:
    print(r.summary())
```

### Regression tracking

```bash
tiny-eval regression bug-fix cursor 0.65
# Regression check for cursor on bug-fix:
#   Trend: regressing 📉
#   Delta: -8.0%
#   Is regression: True
#   ⚠️  WARNING: Score regression detected!
```

---

## Pre-built Suites

`tiny-eval` ships with three standard suites:

| Suite | Description | Threshold |
|-------|-------------|-----------|
| `bug-fix` | Compiles, tests pass, no regressions, no secrets | 75% |
| `code-quality` | Lint, types, coverage, static analysis | 75% |
| `security` | No secrets, no injection, no path traversal | 100% |

```python
from tiny_eval import get_evaluator

ev = get_evaluator()  # standard suites auto-registered
result = ev.run("security", "agent-x", "run-1", context)
```

---

## CLI Reference

```bash
tiny-eval list [suite]           # List eval results
tiny-eval run <suite> <agent> <run_id> [ctx.json]  # Run one eval
tiny-eval report [--format md|json|summary] [suite]  # Generate report
tiny-eval suites                 # List registered suites
tiny-eval regression <suite> <agent> <score>  # Check for regression
```

---

## API Reference

### Criterion

```python
Criterion(
    name="compiles",
    description="Code must compile without errors",
    check=lambda ctx: ctx.get("compile_error") is None,
    weight=1.0,       # contribution to overall score
    required=False,   # if True, fail = immediate FAIL regardless of score
)
```

`check` can return:
- `bool` — True = pass, False = fail
- `tuple[bool, str]` — (passed, message) for richer detail

### EvalSuite

```python
EvalSuite(name, criteria: list[Criterion], pass_threshold=0.7)
```

### Evaluator

```python
get_evaluator() -> Evaluator  # singleton
ev.register_suite(suite)
ev.run(suite_name, agent_name, run_id, context, metadata=None) -> EvalResult
ev.run_batch(suite_name, agent_name, contexts) -> list[EvalResult]
ev.regression_check(suite_name, agent_name, current_score) -> dict
ev.generate_report(format="markdown", suite_name=None, agent_name=None) -> str
```

---

## Example: CI Integration

```python
# In your CI pipeline after an agent PR:
from tiny_eval import eval_run

context = {
    "compile_error": None,
    "test_failures": 0,
    "secrets_found": 0,
    "regression_count": 0,
    "crashed": False,
    "duration_s": 180,
}

result = eval_run("bug-fix", "cursor-agent", "pr-1337", context)
if not result.overall_pass:
    print("Eval failed — block merge")
    exit(1)
print("Eval passed — safe to merge")
```

---

## Eval Result Format

```json
{
  "eval_id": "a1b2c3d4",
  "suite_name": "bug-fix",
  "agent_name": "cursor",
  "run_id": "pr-1337",
  "timestamp": 1723632000.0,
  "timestamp_iso": "2024-08-14T13:00:00",
  "criteria": [
    {
      "name": "compiles",
      "grade": "pass",
      "score": 1.0,
      "message": "clean build",
      "details": {"description": "Code must compile without errors"},
      "duration_ms": 120.5
    }
  ],
  "overall_pass": true,
  "overall_score": 1.0,
  "grade": "pass",
  "total_duration_ms": 2.3,
  "metadata": {}
}
```

---

## Storage

Results are stored in `~/.tiny-eval/` by default:

```
.tiny-eval/
├── .index.jsonl        # Run index
└── {eval_id}.json     # Individual results
```

---

## Why Zero Dependencies?

Eval frameworks need to be trustworthy. If your eval tool has 47 transitive dependencies and one of them silently breaks your CI — you have a new problem on top of your old one.

`tiny-eval` is one file. You can audit it in an afternoon.

---

MIT © 2026 Hussain Al-Saibai
