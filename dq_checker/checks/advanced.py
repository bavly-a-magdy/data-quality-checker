"""Cross-field rules, outliers, and category consistency checks."""
from __future__ import annotations
import ast
import re
import pandas as pd
from .duplicates import ISSUE_COLUMNS
from .missing import is_missing
from .types import infer_type, valid_date, valid_number


def _number(value: str) -> float:
    """Convert common numeric text to a float for safe rule evaluation."""
    text = value.strip()
    if "," in text and "." in text:
        text = text.replace(",", "") if text.rfind(".") > text.rfind(",") else text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def infer_arithmetic_rules(frame: pd.DataFrame, tolerance: float = 0.01, minimum_ratio: float = 0.99) -> list[str]:
    """Infer A = B * C rules supported by at least 99% of complete rows."""
    numeric: dict[str, pd.Series] = {}
    for column in frame.columns:
        values = []
        for value in frame[column]:
            text = str(value)
            if is_missing(text) or not valid_number(text):
                values.append(float("nan"))
            else:
                try: values.append(_number(text))
                except ValueError: values.append(float("nan"))
        series = pd.Series(values, index=frame.index, dtype=float)
        if series.notna().any(): numeric[column] = series
    rules = []
    columns = list(numeric)
    for target in columns:
        for left_index, left in enumerate(columns):
            if left == target: continue
            for right in columns[left_index + 1:]:
                if right == target: continue
                complete = numeric[target].notna() & numeric[left].notna() & numeric[right].notna()
                count = int(complete.sum())
                if not count: continue
                matches = (numeric[target][complete] - numeric[left][complete] * numeric[right][complete]).abs() <= tolerance
                if float(matches.mean()) >= minimum_ratio:
                    rules.append(f"{target} = {left} * {right}")
    return rules


def _compile_rule(rule: str, columns: list[str]) -> tuple[ast.Expression, dict[str, str]]:
    """Replace column labels with safe names, then parse a limited expression."""
    names: dict[str, str] = {}
    expression = re.sub(r"(?<![<>=!])=(?!=)", "==", rule)
    for index, column in enumerate(sorted(columns, key=len, reverse=True)):
        alias = f"col_{index}"
        pattern = rf"(?<![\w]){re.escape(column)}(?![\w])"
        if re.search(pattern, expression):
            expression = re.sub(pattern, alias, expression)
            names[alias] = column
    tree = ast.parse(expression, mode="eval")
    allowed = (ast.Expression, ast.Compare, ast.BinOp, ast.Name, ast.Load, ast.Constant, ast.Mult, ast.Div, ast.Add, ast.Sub, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.USub, ast.UAdd)
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise ValueError("Rule uses unsupported syntax")
    if not set(names).issuperset(node.id for node in ast.walk(tree) if isinstance(node, ast.Name)):
        raise ValueError("Rule refers to a column that was not found")
    return tree, names


def _eval(node: ast.AST, values: dict[str, float]) -> float | bool:
    """Evaluate only the arithmetic and comparisons permitted by the parser."""
    if isinstance(node, ast.Expression): return _eval(node.body, values)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return float(node.value)
    if isinstance(node, ast.Name): return values[node.id]
    if isinstance(node, ast.UnaryOp): return -_eval(node.operand, values) if isinstance(node.op, ast.USub) else _eval(node.operand, values)
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, values), _eval(node.right, values)
        if isinstance(node.op, ast.Add): return left + right
        if isinstance(node.op, ast.Sub): return left - right
        if isinstance(node.op, ast.Mult): return left * right
        if isinstance(node.op, ast.Div): return left / right
    if isinstance(node, ast.Compare):
        left, right = _eval(node.left, values), _eval(node.comparators[0], values)
        op = node.ops[0]
        if isinstance(op, ast.Eq): return abs(left - right) <= 0.01
        if isinstance(op, ast.NotEq): return left != right
        if isinstance(op, ast.Lt): return left < right
        if isinstance(op, ast.LtE): return left <= right
        if isinstance(op, ast.Gt): return left > right
        if isinstance(op, ast.GtE): return left >= right
    raise ValueError("Rule could not be evaluated")


def _recover(rule_tree: ast.Expression, aliases: dict[str, str], row: pd.Series) -> tuple[str, float] | None:
    """Solve for one missing value in a linear equality rule."""
    body = rule_tree.body
    if not isinstance(body, ast.Compare) or len(body.ops) != 1 or not isinstance(body.ops[0], ast.Eq): return None
    names = [node.id for node in ast.walk(body) if isinstance(node, ast.Name)]
    missing = [name for name in dict.fromkeys(names) if name in aliases and is_missing(row[aliases[name]])]
    if len(missing) != 1: return None
    variable = missing[0]
    try:
        known = {alias: _number(str(row[column])) for alias, column in aliases.items() if alias != variable and not is_missing(row[column])}
        def difference(candidate: float) -> float:
            values = {**known, variable: candidate}
            return float(_eval(body.left, values)) - float(_eval(body.comparators[0], values))
        at_zero, at_one, at_two = difference(0.0), difference(1.0), difference(2.0)
        slope = at_one - at_zero
        if abs((at_two - at_one) - slope) > max(1e-8, abs(slope) * 1e-8) or abs(slope) < 1e-12: return None
        value = -at_zero / slope
    except (ValueError, ZeroDivisionError, KeyError, OverflowError): return None
    return aliases[variable], value


def _matching_rule_rows(frame: pd.DataFrame, column: str, rules: list[str]) -> set[int]:
    """Find rows where a configured rule involving a column evaluates true."""
    passing: set[int] = set()
    for rule in rules:
        try: tree, aliases = _compile_rule(rule, list(frame.columns))
        except (SyntaxError, ValueError): continue
        if column not in aliases.values(): continue
        for index, row in frame.iterrows():
            if any(is_missing(row[name]) for name in aliases.values()): continue
            try:
                values = {alias: _number(str(row[name])) for alias, name in aliases.items()}
                if bool(_eval(tree, values)): passing.add(int(index))
            except (ValueError, ZeroDivisionError, KeyError, OverflowError): continue
    return passing


def check_recoverable(frame: pd.DataFrame, file_name: str, rules: list[str]) -> pd.DataFrame:
    """Suggest values for missing cells solvable from configured rules."""
    rows = []
    for rule in rules:
        try: tree, aliases = _compile_rule(rule, list(frame.columns))
        except (SyntaxError, ValueError): continue
        for index, row in frame.iterrows():
            recovered = _recover(tree, aliases, row)
            if recovered is None: continue
            column, value = recovered
            rows.append({"file": file_name, "row number": int(index) + 2, "column": column, "suggested value": value, "rule used": rule})
    result = pd.DataFrame(rows, columns=["file", "row number", "column", "suggested value", "rule used"])
    return result.drop_duplicates(subset=["file", "row number", "column"], keep="first").reset_index(drop=True)


def check_cross_field(frame: pd.DataFrame, file_name: str, rules: list[str]) -> pd.DataFrame:
    """Report configured arithmetic rule violations."""
    rows = []
    for rule in rules:
        try: tree, aliases = _compile_rule(rule, list(frame.columns))
        except (SyntaxError, ValueError) as exc:
            if not any(re.search(rf"(?<![\w]){re.escape(column)}(?![\w])", rule) for column in frame.columns): continue
            rows.append({"file": file_name, "row number": "", "column": "", "bad value": rule, "issue type": "invalid cross-field rule", "explanation": str(exc)})
            continue
        for index, row in frame.iterrows():
            cols = list(aliases.values())
            if any(is_missing(row[col]) for col in cols): continue
            try:
                values = {alias: _number(str(row[column])) for alias, column in aliases.items()}
                valid = bool(_eval(tree, values))
            except (ValueError, ZeroDivisionError, KeyError, OverflowError): continue
            if not valid:
                rows.append({"file": file_name, "row number": int(index) + 2, "column": ", ".join(cols), "bad value": " | ".join(str(row[col]) for col in cols), "issue type": "cross-field rule violation", "explanation": f"Values do not satisfy: {rule}"})
    return pd.DataFrame(rows, columns=ISSUE_COLUMNS)


def check_outliers(frame: pd.DataFrame, file_name: str, rules: list[str] | None = None) -> pd.DataFrame:
    """Flag values beyond 3 IQRs unless their configured rule validates them."""
    rows = []
    rules = rules or []
    for column in frame.columns:
        valid_rows = _matching_rule_rows(frame, column, rules)
        values = [(index, str(value)) for index, value in frame[column].items() if not is_missing(value) and valid_number(str(value))]
        if len(values) < 4: continue
        parsed = pd.Series({index: _number(value) for index, value in values}, dtype=float)
        q1, q3 = parsed.quantile(.25), parsed.quantile(.75)
        spread = q3 - q1
        if spread == 0: continue
        lower, upper = q1 - 3 * spread, q3 + 3 * spread
        for index, value in values:
            number = parsed.loc[index]
            if (number < lower or number > upper) and int(index) not in valid_rows:
                rows.append({"file": file_name, "row number": int(index) + 2, "column": column, "bad value": value, "issue type": "review", "explanation": f"Review value outside the 3 × IQR range ({lower:g} to {upper:g}); this is a review flag, not an error."})
    return pd.DataFrame(rows, columns=ISSUE_COLUMNS)

def check_categories(frame: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Flag text categories that differ only by case or surrounding whitespace."""
    rows = []
    for column in frame.columns:
        if infer_type(frame[column].astype(str).tolist()) != "text": continue
        groups: dict[str, list[tuple[int, str]]] = {}
        for index, value in frame[column].items():
            text = str(value)
            if is_missing(text): continue
            normalized = text.strip().casefold()
            groups.setdefault(normalized, []).append((index, text))
        for variants in groups.values():
            spellings = {value for _, value in variants}
            if len(spellings) < 2: continue
            for index, value in variants:
                rows.append({"file": file_name, "row number": int(index) + 2, "column": column, "bad value": value, "issue type": "inconsistent category", "explanation": f"Category varies in case or whitespace: {', '.join(sorted(spellings))}"})
    return pd.DataFrame(rows, columns=ISSUE_COLUMNS)
