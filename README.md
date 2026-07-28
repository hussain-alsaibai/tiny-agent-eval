# tiny-eval — Zero-Dependency Sandboxed Expression Evaluator

> **Like `eval()` but safe. For dynamic configs, rule engines, and agent tool parameters.**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](tiny_eval.py)

## Why?

Every agent needs to evaluate dynamic expressions — rule conditions, config
interpolation, tool parameter computation. `eval()` is dangerous. Jinja2 is a
dependency. `restrictedpython` is complex.

`tiny-eval` is 280 lines, zero deps, and sandboxed by default:

```python
from tiny_eval import eval_expr, Sandbox

# Safe: basic math + strings + collections
result = eval_expr("x * 2 + 1", {"x": 7})  # 15

# Sandboxed: blocks file access, imports, syscalls
result = eval_expr(
    "open('/etc/passwd').read()",
    sandbox=Sandbox(strict=True)
)  # raises EvalError: Access denied

# With timeout (Unix)
result = eval_expr("sum(range(10**8))", timeout=1.0)
# raises TimeoutError after 1 second

# Interpolate templates: {{variable}} substitution
from tiny_eval import interpolate
interpolate("Hello, {{ name }}!", name="Alice")  # "Hello, Alice!"
```

## Features

- **🔒 Sandboxed** — blocks dangerous builtins, imports, file access, syscalls
- **⏱️ Timeout enforcement** — SIGALRM guard (Unix); prevents infinite loops
- **🔧 Config expressions** — evaluate `int(env["PORT"]) if env else 8080`
- **📝 Template interpolation** — `{{variable}}` without Jinja2
- **🪶 Zero dependencies** — stdlib only
- **📦 Single file** — drop anywhere

## Sandbox Levels

```python
Sandbox()             # relaxed: math, str, list, dict, json, re, datetime
Sandbox(strict=True)  # strict: only math + basic types
Sandbox(allowed_builtins={"json": json_module})
```

## API

### `eval_expr(source, globals=None, *, sandbox=None, timeout=None)`

Evaluate a single expression and return its result.

### `eval_stmt(source, globals=None, *, sandbox=None, timeout=None)`

Execute one or more statements and return the final namespace.

### `Sandbox(*, strict=False, allowed_builtins=None, allowed_modules=None, ...)`

Configure the security policy applied to expressions.

### `interpolate(text, **variables)`

`{{name}}`-style template substitution without a template engine.

### `evaluate_config_expr(expr, variables, *, strict=True)`

Evaluate a config expression with helpful defaults (see helper for usage).

## Install

```bash
pip install tiny-eval          # not yet, it's a single file
# Just copy tiny_eval.py into your project:
cp tiny_eval.py your_project/
```

Or use it directly:

```python
from tiny_eval import eval_expr
print(eval_expr("2 + 2"))  # 4
```

## Tests

```bash
python -m pytest test_tiny_eval.py -x -q
```

## License

MIT — see [LICENSE](LICENSE).

## Ecosystem

Part of the **tiny-*** zero-dependency toolkit. See also:
[**tiny-config**](https://github.com/hussain-alsaibai/tiny-config),
[**tiny-validator**](https://github.com/hussain-alsaibai/tiny-validator),
[**tiny-log**](https://github.com/hussain-alsaibai/tiny-log),
[**tiny-agent**](https://github.com/hussain-alsaibai/tiny-agent).

Built by [OpenClaw](https://github.com/hussain-alsaibai).
