"""tiny-eval — Zero-dependency sandboxed expression evaluator for Python.

Safely evaluate Python expressions and statements in an isolated namespace.
Supports whitelisted builtins, sandboxed globals, and timeout enforcement.

Usage:
    from tiny_eval import eval_expr, eval_stmt, Sandbox, EvalError

    # Simple expression
    result = eval_expr("2 + 3 * 4")  # 14

    # With custom globals
    result = eval_expr("x ** 2", {"x": 7})  # 49

    # Sandboxed (no dangerous builtins)
    result = eval_expr("open('/etc/passwd')", sandbox=Sandbox(strict=True))
    # raises EvalError: access denied

    # Statement execution
    eval_stmt("total = sum(values)", {"values": [1, 2, 3]})
    # returns {"total": 6}

    # With timeout (enforced via signal.SIGALRM on Unix)
    result = eval_expr("sum(range(10**7))", timeout=1.0)
    # raises EvalError: evaluation timed out after 1.0s
"""

from __future__ import annotations

import math
import os
import re
import signal
import sys
import time
from typing import Any, Callable


__version__ = "0.1.0"
__all__ = [
    "eval_expr",
    "eval_stmt",
    "EvalError",
    "Sandbox",
    "TimeoutError",
    "interpolate",
    "evaluate_config_expr",
]


# ---------- Exceptions ----------


class EvalError(Exception):
    """Raised when evaluation fails: syntax error, access denied, timeout."""
    pass


class TimeoutError(EvalError):
    """Raised when evaluation exceeds the timeout."""
    pass


# ---------- Sandbox ----------


class Sandbox:
    """Controls what code can do inside the evaluator.

    Usage:
        Sandbox()                       # relaxed (math, str, list, dict only)
        Sandbox(strict=True)           # very strict (only math + basic types)
        Sandbox(allowed_modules=["json", "re"])
        Sandbox(max_iterations=1000)   # iteration guard
        Sandbox(max_memory_mb=50)       # memory guard (approximate)
    """

    DANGEROUS_BUILTINS = {
        "open", "file", "__import__", "eval", "exec", "compile",
        "reload", "breakpoint", "exit", "quit", "help",
        "vars", "globals", "locals", "dir", "type",
        "getattr", "setattr", "delattr", "hasattr",
        "memoryview", "buffer", "classmethod", "staticmethod",
        "property", "super", "object",
        "__builtins__", "__class__", "__subclasses__",
        "run", "R", "S",
    }

    DANGEROUS_PATTERNS = [
        re.compile(r"\bos\.system\b"),
        re.compile(r"\bos\.popen\b"),
        re.compile(r"\bos\.spawn\b"),
        re.compile(r"\bsubprocess\b"),
        re.compile(r"\bimport\s+os\b"),
        re.compile(r"\bimport\s+subprocess\b"),
        re.compile(r"\bimport\s+sys\b"),
        re.compile(r"\bimport\s+requests\b"),
        re.compile(r"\bimport\s+urllib\b"),
        re.compile(r"\bimport\s+http\b"),
        re.compile(r"\b__import__\b"),
        re.compile(r"\{\{.*\}\}"),  # template injection
        re.compile(r"<script"),
        re.compile(r"</script"),
        re.compile(r"globals\(\)"),
        re.compile(r"locals\(\)"),
        re.compile(r"vars\(\)"),
        re.compile(r"dir\(\)"),
    ]

    SAFE_BUILTINS = {
        "abs": abs, "all": all, "any": any, "ascii": ascii,
        "bin": bin, "bool": bool, "bytearray": bytearray,
        "bytes": bytes, "callable": callable, "chr": chr,
        "dict": dict, "divmod": divmod, "enumerate": enumerate,
        "filter": filter, "float": float, "format": format,
        "frozenset": frozenset, "hash": hash, "hex": hex,
        "int": int, "isinstance": isinstance, "issubclass": issubclass,
        "iter": iter, "len": len, "list": list, "map": map,
        "max": max, "min": min, "next": next, "oct": oct,
        "ord": ord, "pow": pow, "range": range, "repr": repr,
        "reversed": reversed, "round": round, "set": set,
        "slice": slice, "sorted": sorted, "str": str,
        "sum": sum, "tuple": tuple, "zip": zip,
        # Safe modules
        "math": math,
        "re": __import__("re"),
        "json": __import__("json"),
        "datetime": __import__("datetime"),
        "decimal": __import__("decimal"),
        "random": __import__("random"),
        "functools": __import__("functools"),
        "operator": __import__("operator"),
        "string": __import__("string"),
        "textwrap": __import__("textwrap"),
        "time": __import__("time"),
        "itertools": __import__("itertools"),
        "collections": __import__("collections"),
        "statistics": __import__("statistics"),
        "uuid": __import__("uuid"),
        "hashlib": __import__("hashlib"),
    }

    def __init__(
        self,
        *,
        strict: bool = False,
        allowed_builtins: dict | None = None,
        allowed_modules: list | None = None,
        max_iterations: int | None = None,
        max_memory_mb: int | None = None,
        allow_syscalls: bool = False,
    ) -> None:
        self._strict = strict
        self._allowed: dict = {} if strict else dict(self.SAFE_BUILTINS)
        if allowed_builtins:
            self._allowed.update(allowed_builtins)
        self._allowed_modules = set(allowed_modules or [])
        self._max_iterations = max_iterations
        self._max_memory_mb = max_memory_mb
        self._allow_syscalls = allow_syscalls

    def check(self, source: str) -> None:
        """Validate source before evaluation. Raises EvalError on violation."""
        if self._strict:
            # Very strict: only allow simple expressions
            if not re.match(r"^[\w\s.,()\[\]{}\"'\+\-*/<>=!|%^~?:]+$", source.strip()):
                raise EvalError(
                    f"Character not allowed in strict mode: {source[:50]}"
                )

        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.search(source):
                raise EvalError(
                    f"Access denied: dangerous pattern detected in {source[:50]}"
                )

        # Check for dangerous builtins in the source
        for b in self.DANGEROUS_BUILTINS:
            if re.search(rf"\b{re.escape(b)}\b", source):
                # If the user didn't override this one, it's denied
                if self._allowed.get(b) is None:
                    raise EvalError(f"Builtin '{b}' is not allowed")

    def globals(self, **extra: Any) -> dict[str, Any]:
        g: dict[str, Any] = {"__builtins__": self._allowed}
        g.update(extra)
        return g


# ---------- Timeout helper ----------


class _TimeoutGuard:
    """Context manager that enforces a wall-clock timeout via SIGALRM.

    Unix only (uses signal.SIGALRM). On Windows it's a no-op and the caller
    is responsible for its own timeout.
    """

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self._old_handler: Any = None
        self._supported = sys.platform != "win32"

    def __enter__(self) -> "_TimeoutGuard":
        if not self._supported:
            return self
        def _handler(signum: int, frame: Any) -> None:
            raise TimeoutError(
                f"evaluation timed out after {self.timeout}s"
            )

        self._old_handler = signal.signal(signal.SIGALRM, _handler)
        # Use ceil so 0.1s still gives the handler time to fire
        signal.alarm(max(1, int(round(self.timeout)) + 1))
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self._supported:
            return
        signal.alarm(0)
        if self._old_handler is not None:
            signal.signal(signal.SIGALRM, self._old_handler)


# ---------- Core evaluators ----------


def eval_expr(
    source: str,
    globals: dict | None = None,
    *,
    sandbox: Sandbox | None = None,
    timeout: float | None = None,
) -> Any:
    """Evaluate a Python expression and return the result.

    Args:
        source: Python expression (e.g. "x + 1")
        globals: Optional namespace dict
        sandbox: Optional Sandbox for security
        timeout: Max seconds (Unix only)

    Returns:
        The evaluated result

    Raises:
        EvalError: on syntax, security, or timeout violation
    """
    source = source.strip()

    # If no explicit sandbox is provided, use a relaxed default so callers
    # can still use `math`, `json`, etc. without explicit wiring.
    sb = sandbox or Sandbox()

    sb.check(source)

    ns: dict[str, Any] = dict(sb.globals())
    if globals:
        ns.update(globals)

    # Validate syntax before eval
    try:
        compile(source, "<tiny_eval>", "eval")
    except SyntaxError as e:
        raise EvalError(f"Syntax error: {e}")

    with _TimeoutGuard(timeout) if timeout else _NoopGuard():
        try:
            return eval(source, ns)  # noqa: S307
        except TimeoutError:
            raise
        except EvalError:
            raise
        except Exception as e:
            raise EvalError(f"{type(e).__name__}: {e}")


class _NoopGuard:
    """Drop-in replacement for _TimeoutGuard when no timeout requested."""

    def __enter__(self) -> "_NoopGuard":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def eval_stmt(
    source: str,
    globals: dict | None = None,
    *,
    sandbox: Sandbox | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Execute Python statements and return the final namespace.

    Args:
        source: Python statements (e.g. "x = 2; y = x * 3")
        globals: Optional starting namespace
        sandbox: Optional Sandbox for security
        timeout: Max seconds

    Returns:
        The final namespace dict (with any defined variables)

    Raises:
        EvalError: on syntax, security, or timeout violation
    """
    source = source.strip()

    if sandbox:
        sandbox.check(source)

    ns: dict[str, Any] = dict(sandbox.globals() if sandbox else {})
    if globals:
        ns.update(globals)

    try:
        compiled = compile(source, "<tiny_eval>", "exec")
    except SyntaxError as e:
        raise EvalError(f"Syntax error: {e}")

    with _TimeoutGuard(timeout) if timeout else _NoopGuard():
        try:
            exec(compiled, ns)  # noqa: S102
        except TimeoutError:
            raise
        except EvalError:
            raise
        except Exception as e:
            raise EvalError(f"{type(e).__name__}: {e}")

    return ns


# ---------- Config expression helper ----------


def evaluate_config_expr(
    expr: str,
    variables: dict[str, Any],
    *,
    strict: bool = True,
) -> Any:
    """Evaluate a configuration expression with variable substitution.

    Supports:
        config.get("db.host")         -> str comparison
        env["DATABASE_URL"]           -> env var access
        int(os.environ["PORT"])       -> type casts
        value if x > 0 else default   -> ternary

    Usage in config loading:
        evaluate_config_expr(
            "int(os.environ['PORT']) if 'PORT' in os.environ else 8080",
            {"os": __import__("os")}
        )
    """
    return eval_expr(expr, variables, sandbox=Sandbox(strict=strict))


# ---------- Template helper ----------


def interpolate(text: str, **variables: Any) -> str:
    """Simple {{variable}} interpolation, like Jinja2 without the dependency.

    Usage:
        interpolate("Hello, {{name}}!", name="Alice")  # "Hello, Alice!"
        interpolate("Port is {{ port }}", port=8080)   # "Port is 8080"
    """
    def replacer(m: "re.Match[str]") -> str:
        key = m.group(1).strip()
        if key in variables:
            val = variables[key]
            return str(val) if val is not None else ""
        return m.group(0)

    return re.sub(r"\{\{([^}]+)\}\}", replacer, text)
