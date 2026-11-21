"""Date and numeric format validation."""
from __future__ import annotations
from datetime import date, datetime
import re
import pandas as pd
from .duplicates import ISSUE_COLUMNS
from .missing import is_missing
from .types import DATE_FORMATS, infer_type, valid_date, valid_number
CURRENCY=re.compile(r"[$€£¥₹]")
def date_format(value: str) -> str | None:
    for fmt in DATE_FORMATS:
        try: datetime.strptime(value.strip(),fmt); return fmt
        except ValueError: pass
    return None
def check_formats(frame: pd.DataFrame, file_name: str, config: dict | None = None) -> pd.DataFrame:
    """Flag invalid or mixed dates and suspicious numeric formatting."""
    rows=[]; config=config or {}; nonnegative=set(config.get("non_negative",[]))
    def add(idx,col,value,issue,why): rows.append({"file":file_name,"row number":int(idx)+2,"column":col,"bad value":str(value),"issue type":issue,"explanation":why})
    for col in frame.columns:
        vals=[str(v) for v in frame[col] if not is_missing(v)]
        kind=infer_type(vals)
        if kind=="date":
            formats={date_format(v) for v in vals if date_format(v)}
            mixed=len(formats)>1
            for idx,value in frame[col].items():
                val=str(value)
                if is_missing(val): continue
                parsed = date_format(val)
                if not parsed: add(idx,col,val,"invalid date","Value is not a valid supported date")
                else:
                    try: parsed_date = datetime.strptime(val.strip(), parsed).date()
                    except ValueError: parsed_date = None
                    if parsed_date and parsed_date > date.today(): add(idx,col,val,"future date","Date is later than today")
                    if mixed: add(idx,col,val,"mixed date format","Date format differs from other values in this column")
        numeric=[(idx,str(v)) for idx,v in frame[col].items() if not is_missing(v) and (valid_number(str(v)) or CURRENCY.search(str(v)))]
        if numeric:
            conventions=set()
            for _,v in numeric:
                if "," in v and "." in v: conventions.add("mixed separators")
                elif "," in v: conventions.add("comma")
                elif "." in v: conventions.add("dot")
            mixed_separator=len(conventions)>1 or "mixed separators" in conventions
            for idx,val in numeric:
                if CURRENCY.search(val): add(idx,col,val,"currency symbol","Currency symbol is embedded in a numeric column")
                if mixed_separator: add(idx,col,val,"mixed number separators","Number punctuation differs within this numeric column")
                try:
                    normalized=val.replace(",","") if "," in val and "." in val else val.replace(",",".")
                    if col in nonnegative and float(normalized)<0: add(idx,col,val,"negative in non-negative column","Configuration requires this column to be zero or greater")
                except ValueError: pass
    return pd.DataFrame(rows,columns=ISSUE_COLUMNS)
