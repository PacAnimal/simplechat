import ast
import math
import operator

_SAFE_OPS: dict = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS: dict = {
    "sqrt": math.sqrt,
    "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "factorial": math.factorial,
    "degrees": math.degrees,
    "radians": math.radians,
    "hypot": math.hypot,
    "gcd": math.gcd,
}

_SAFE_CONSTS: dict = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}


def _eval_node(node: ast.expr) -> float | int:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"unsupported literal: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in _SAFE_CONSTS:
            return _SAFE_CONSTS[node.id]
        raise ValueError(f"unknown name: {node.id!r}")
    if isinstance(node, ast.BinOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("only simple function calls are supported")
        func_name = node.func.id
        if func_name not in _SAFE_FUNCS:
            raise ValueError(f"unknown function: {func_name!r}")
        if node.keywords:
            raise ValueError("keyword arguments are not supported")
        args = [_eval_node(a) for a in node.args]
        return _SAFE_FUNCS[func_name](*args)  # type: ignore
    raise ValueError(f"unsupported expression type: {type(node).__name__}")


def calculate(expression: str) -> dict:
    """Safely evaluate a mathematical expression and return result with formatted text."""
    expression = expression.strip()
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
            formatted = str(int(result))
        elif isinstance(result, float):
            formatted = repr(result)
        else:
            formatted = str(result)
        return {
            "result": result,
            "expression": expression,
            "text": f"{expression} = {formatted}",
        }
    except ZeroDivisionError:
        msg = "division by zero"
        return {"error": msg, "expression": expression, "text": f"Error evaluating '{expression}': {msg}"}
    except (ValueError, TypeError) as exc:
        return {"error": str(exc), "expression": expression, "text": f"Error evaluating '{expression}': {exc}"}
    except SyntaxError:
        msg = "invalid syntax"
        return {"error": msg, "expression": expression, "text": f"Error evaluating '{expression}': {msg}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "expression": expression, "text": f"Error evaluating '{expression}': {exc}"}
