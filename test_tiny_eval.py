"""Tests for tiny-eval."""
import sys
import pytest

from tiny_eval import (
    eval_expr,
    eval_stmt,
    EvalError,
    Sandbox,
    TimeoutError,
    interpolate,
    evaluate_config_expr,
)


class TestEvalExpr:
    def test_arithmetic(self):
        assert eval_expr("2 + 3") == 5
        assert eval_expr("10 / 2") == 5.0
        assert eval_expr("2 ** 8") == 256
        assert eval_expr("(1 + 2) * 3") == 9

    def test_with_globals(self):
        assert eval_expr("x * 2", {"x": 7}) == 14
        assert eval_expr("name.upper()", {"name": "alice"}) == "ALICE"

    def test_list_comprehension(self):
        assert eval_expr("[x*2 for x in range(5)]") == [0, 2, 4, 6, 8]

    def test_math_module(self):
        assert abs(eval_expr("math.sqrt(16)") - 4.0) < 0.0001
        assert eval_expr("math.pi") > 3.14

    def test_dict_access(self):
        assert eval_expr('d["key"]', {"d": {"key": 42}}) == 42

    def test_string_method(self):
        assert eval_expr('",".join(["a", "b", "c"])') == "a,b,c"

    def test_safe_with_sandbox(self):
        s = Sandbox()
        assert eval_expr("len([1, 2, 3])", sandbox=s) == 3
        assert eval_expr("sum([1, 2, 3])", sandbox=s) == 6


class TestSandbox:
    def test_blocks_dangerous_builtins(self):
        s = Sandbox(strict=True)
        with pytest.raises(EvalError):
            eval_expr("open('/etc/passwd')", sandbox=s)

    def test_blocks_import(self):
        s = Sandbox()
        with pytest.raises(EvalError):
            eval_expr("__import__('os')", sandbox=s)

    def test_blocks_subprocess_text(self):
        s = Sandbox()
        with pytest.raises(EvalError):
            eval_expr("import subprocess; subprocess.run(['ls'])", sandbox=s)

    def test_blocks_os_system(self):
        # The os-system pattern check trips before eval even with sandbox=None,
        # but here we use a sandbox to verify the path stays consistent.
        s = Sandbox()
        with pytest.raises(EvalError):
            eval_expr(
                "os.system('ls')",
                {"os": __import__("os")},
                sandbox=s,
            )

    def test_allows_safe_builtins(self):
        s = Sandbox()
        assert eval_expr("len([1,2,3])", sandbox=s) == 3
        assert eval_expr("str(42)", sandbox=s) == "42"
        assert eval_expr("abs(-7)", sandbox=s) == 7

    def test_strict_mode_basic_math(self):
        s = Sandbox(strict=True)
        assert eval_expr("x + 1", {"x": 5}, sandbox=s) == 6
        assert eval_expr("2 + 3 * 4", sandbox=s) == 14

    def test_strict_mode_blocks_unsafe(self):
        s = Sandbox(strict=True)
        with pytest.raises(EvalError):
            eval_expr("__import__('os')", sandbox=s)

    def test_globals_provider(self):
        s = Sandbox()
        ns = s.globals(x=42)
        assert ns["x"] == 42
        assert ns["__builtins__"] is not None


class TestEvalStmt:
    def test_assignments(self):
        ns = eval_stmt("x = 10; y = 20; total = x + y")
        assert ns["total"] == 30

    def test_conditionals(self):
        ns = eval_stmt("if True:\n    x = 1\nelse:\n    x = 2")
        assert ns["x"] == 1

    def test_with_globals(self):
        ns = eval_stmt("total = sum(values)", {"values": [1, 2, 3]})
        assert ns["total"] == 6

    def test_returns_namespace(self):
        ns = eval_stmt("a = 1")
        assert "a" in ns


class TestInterpolate:
    def test_basic(self):
        assert interpolate("Hello, {{ name }}!", name="Alice") == "Hello, Alice!"
        assert interpolate("Port: {{ port }}", port=8080) == "Port: 8080"

    def test_missing_variable(self):
        assert interpolate("Hi, {{ name }}", notname="Bob") == "Hi, {{ name }}"

    def test_multiple_vars(self):
        out = interpolate(
            "{{greeting}}, {{name}}! You are {{age}}.",
            greeting="Hello",
            name="Alice",
            age=30,
        )
        assert out == "Hello, Alice! You are 30."

    def test_none_value_renders_empty(self):
        out = interpolate("A={{x}}B", x=None)
        assert out == "A=B"


class TestTimeout:
    def test_timeout_enforced(self):
        if sys.platform == "win32":
            pytest.skip("timeout uses SIGALRM (Unix only)")
        # SIGALRM has 1s granularity; compute must exceed that.
        with pytest.raises(TimeoutError):
            eval_expr("sum(range(10**9))", timeout=1.0)

    def test_no_timeout_when_not_specified(self):
        # Should not raise anything
        result = eval_expr("sum(range(100))")
        assert result == sum(range(100))


class TestErrors:
    def test_syntax_error(self):
        with pytest.raises(EvalError):
            eval_expr("def +++")  # syntax garbage

    def test_runtime_error_wrapped(self):
        with pytest.raises(EvalError) as ei:
            eval_expr("1/0")
        assert "ZeroDivisionError" in str(ei.value)


class TestEvaluateConfigExpr:
    def test_ternary(self):
        result = evaluate_config_expr(
            "x if x > 0 else 0",
            {"x": 5},
        )
        assert result == 5

    def test_fallback(self):
        result = evaluate_config_expr(
            "x if x > 0 else 0",
            {"x": -1},
        )
        assert result == 0
