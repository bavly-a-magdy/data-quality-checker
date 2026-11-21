"""Type inference and mismatch checks."""
from __future__ import annotations
from datetime import datetime
import re
import pandas as pd
from .duplicates import ISSUE_COLUMNS
from .missing import is_missing
NUM_RE=re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)*|[.,]\d+)$")
DATE_FORMATS=("%Y-%m-%d","%Y/%m/%d","%d/%m/%Y","%m/%d/%Y","%d-%m-%Y","%Y-%m-%d %H:%M:%S","%d.%m.%Y")
def valid_number(value: str) -> bool:
    return bool(NUM_RE.match(value.strip()))
def valid_date(value: str) -> bool:
    for fmt in DATE_FORMATS:
        try: datetime.strptime(value.strip(),fmt); return True
        except ValueError: pass
    return False
def infer_type(values: list[str]) -> str:
    """Infer the majority type among valid nonmissing values."""
    vals=[v for v in values if not is_missing(v)]
    if not vals: return "text"
    counts={"number":sum(valid_number(v) for v in vals),"date":sum(valid_date(v) for v in vals)}
    winner=max(counts,key=counts.get)
    return winner if counts[winner] > len(vals)/2 else "text"
def check_types(frame: pd.DataFrame, file_name: str, overrides: dict | None = None) -> pd.DataFrame:
    """Flag values that do not match inferred or configured column types."""
    rows=[]; overrides=overrides or {}
    for col in frame.columns:
        expected=str(overrides.get(col,infer_type(frame[col].astype(str).tolist()))).lower()
        for idx,value in frame[col].items():
            val=str(value)
            if is_missing(val): continue
            okay = valid_number(val) if expected in ("number","numeric","integer","float") else valid_date(val) if expected=="date" else True
            if not okay: rows.append({"file":file_name,"row number":int(idx)+2,"column":col,"bad value":val,"issue type":"type mismatch","explanation":f"Expected {expected} value based on column type"})
    return pd.DataFrame(rows,columns=ISSUE_COLUMNS)
