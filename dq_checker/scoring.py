"""Column and overall quality score calculations."""
from __future__ import annotations
import pandas as pd


def quality_score(total_rows: int, total_columns: int, issue_count: float) -> float:
    """Score equals 100 minus weighted issue rate per cell, bounded from 0 to 100."""
    cells = max(total_rows * total_columns, 1)
    return round(max(0.0, min(100.0, 100.0 - 100.0 * issue_count / cells)), 2)


def column_scores(frame: pd.DataFrame, checks: dict, config: dict | None = None) -> list[dict]:
    """Calculate per-column scores, applying optional-column missing weight."""
    config = config or {}
    optional = set(config.get("optional_columns", []))
    row_count = max(len(frame), 1)
    missing = checks.get("missing")
    summary = {item["column"]: item["missing count"] for item in missing.attrs.get("summary", [])} if missing is not None else {}
    issue_counts = {column: float(summary.get(column, 0)) * (0.25 if column in optional else 1.0) for column in frame.columns}
    for name, table in checks.items():
        if name in ("missing", "recoverable", "outliers"): continue
        for _, issue in table.iterrows():
            if str(issue.get("issue type", "")).lower() == "review": continue
            columns = [part.strip() for part in str(issue.get("column", "")).split(",")]
            for column in columns:
                if column in issue_counts:
                    issue_counts[column] += 1.0
    output = []
    for column in frame.columns:
        weighted_issues = issue_counts[column]
        output.append({"column": column, "weighted issues": round(weighted_issues, 2), "quality score": round(max(0.0, 100.0 - weighted_issues / row_count * 100.0), 2)})
    return output


def overall_score(frame: pd.DataFrame, checks: dict, config: dict | None = None) -> float:
    """Calculate the weighted per-cell score across a file."""
    scores = column_scores(frame, checks, config)
    return quality_score(len(frame), len(frame.columns), sum(row["weighted issues"] for row in scores))
