"""Missing value checks."""
from __future__ import annotations
import pandas as pd
from .duplicates import ISSUE_COLUMNS

MISSING_TOKENS = {"", " ", "NA", "N/A", "null", "None", "-"}

def is_missing(value: object) -> bool:
    """Return whether a source value is one of the supported empty markers."""
    return str(value).strip() in MISSING_TOKENS

def check_missing(frame: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Report one row per affected record and summarize missing cells by column."""
    summary = []
    rows = []
    masks = {column: frame[column].map(is_missing) for column in frame.columns}
    for column, mask in masks.items():
        count = int(mask.sum())
        summary.append({"file": file_name, "column": column, "missing count": count, "missing %": round(count / max(len(frame), 1) * 100, 2)})
    combined = pd.DataFrame(masks, index=frame.index)
    for index in frame.index[combined.any(axis=1)]:
        columns = [column for column in frame.columns if masks[column].at[index]]
        count = len(columns)
        label = "1 empty field" if count == 1 else f"{count} empty fields"
        rows.append({"file": file_name, "row number": int(index) + 2, "column": ", ".join(columns), "bad value": "(empty)", "issue type": "missing value", "explanation": label})
    result = pd.DataFrame(rows, columns=ISSUE_COLUMNS)
    result.attrs["summary"] = summary
    result.attrs["cell_count"] = sum(item["missing count"] for item in summary)
    return result
