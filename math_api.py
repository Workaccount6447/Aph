from flask import Flask, request, jsonify
import math
import operator
import re

app = Flask(__name__)


# ── Safe math evaluator ──────────────────────────────────────────────────────
# Uses a whitelist of allowed names — never calls eval() on raw input.

SAFE_FUNCTIONS = {
    # Basic math
    "abs": abs,
    "round": round,
    "pow": pow,
    "min": min,
    "max": max,
    # math module
    "sqrt":  math.sqrt,
    "cbrt":  lambda x: math.copysign(abs(x) ** (1/3), x),
    "log":   math.log,
    "log2":  math.log2,
    "log10": math.log10,
    "exp":   math.exp,
    "ceil":  math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
    "gcd":   math.gcd,
    # Trig
    "sin":   math.sin,
    "cos":   math.cos,
    "tan":   math.tan,
    "asin":  math.asin,
    "acos":  math.acos,
    "atan":  math.atan,
    "atan2": math.atan2,
    "sinh":  math.sinh,
    "cosh":  math.cosh,
    "tanh":  math.tanh,
    # Degrees / radians
    "degrees": math.degrees,
    "radians": math.radians,
    # Constants
    "pi":  math.pi,
    "e":   math.e,
    "tau": math.tau,
    "inf": math.inf,
}

# Disallow anything that looks like dunder / builtins abuse
_BLOCKED = re.compile(r'__|\bimport\b|\bexec\b|\beval\b|\bopen\b|\bos\b|\bsys\b')


def safe_eval(expression: str):
    """Evaluate a math expression safely."""
    expr = expression.strip()

    if _BLOCKED.search(expr):
        raise ValueError("Expression contains disallowed keywords.")

    # Replace ^ with ** for convenience
    expr = expr.replace("^", "**")

    try:
        result = eval(expr, {"__builtins__": {}}, SAFE_FUNCTIONS)  # noqa: S307
    except ZeroDivisionError:
        raise ValueError("Division by zero.")
    except (SyntaxError, NameError, TypeError) as exc:
        raise ValueError(f"Invalid expression: {exc}")

    if isinstance(result, complex):
        raise ValueError("Result is a complex number — not supported.")
    if result != result:   # NaN check
        raise ValueError("Result is undefined (NaN).")
    if math.isinf(result):
        raise ValueError("Result is infinite.")

    return result


def format_result(value) -> str:
    """Return a clean string — remove unnecessary decimals."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        # Up to 10 significant figures, strip trailing zeros
        return f"{value:.10g}"
    return str(value)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/math", methods=["GET", "POST"])
def math_endpoint():
    """
    GET  /math?q=2+2
    POST /math  body: {"expression": "sqrt(144) + pi"}
    """
    if request.method == "GET":
        expression = request.args.get("q", "").strip()
    else:
        data = request.get_json(silent=True) or {}
        expression = data.get("expression", "").strip()

    if not expression:
        return jsonify({
            "ok": False,
            "error": "No expression provided.",
            "hint": "GET /math?q=2+2  or  POST /math {\"expression\": \"sqrt(144)\"}"
        }), 400

    try:
        result = safe_eval(expression)
        return jsonify({
            "ok": True,
            "expression": expression,
            "result": format_result(result),
            "result_float": float(result),
        })
    except ValueError as exc:
        return jsonify({
            "ok": False,
            "expression": expression,
            "error": str(exc),
        }), 422


@app.route("/math/help", methods=["GET"])
def math_help():
    """List of supported functions and constants."""
    return jsonify({
        "supported_operators": ["+", "-", "*", "/", "//", "%", "**", "^ (alias for **)"],
        "functions": sorted(k for k, v in SAFE_FUNCTIONS.items() if callable(v)),
        "constants": sorted(k for k, v in SAFE_FUNCTIONS.items() if not callable(v)),
        "examples": [
            "2 + 2",
            "sqrt(144)",
            "sin(pi / 2)",
            "log(e)",
            "factorial(10)",
            "2^10",
            "round(3.14159, 2)",
            "floor(9.9)",
            "gcd(48, 18)",
            "degrees(pi)",
        ],
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "math-api"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    port = int(os.getenv("FLASK_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
