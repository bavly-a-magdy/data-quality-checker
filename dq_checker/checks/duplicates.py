"""Duplicate row checks."""
from __future__ import annotations
import pandas as pd
ISSUE_COLUMNS = ["file", "row number", "column", "bad value", "issue type", "explanation"]
def check_duplicates(frame: pd.DataFrame, file_name: str, key_columns: list[str] | None = None) -> pd.DataFrame:
    """Find full-row and optional key duplicates; row numbers include the header offset."""
    rows = []
    for kind, mask in [("duplicate row", frame.duplicated(keep=False)), ("duplicate key", frame.duplicated(subset=key_columns, keep=False) if key_columns else pd.Series(False, index=frame.index))]:
        for idx in frame.index[mask]:
            cols = key_columns if kind == "duplicate key" else list(frame.columns)
            rows.append({"file": file_name, "row number": int(idx)+2, "column": ", ".join(cols), "bad value": " | ".join(str(frame.at[idx,c]) for c in cols), "issue type": kind, "explanation": "This row repeats another row" if kind == "duplicate row" else "These key values appear in another row"})
    return pd.DataFrame(rows, columns=ISSUE_COLUMNS)
