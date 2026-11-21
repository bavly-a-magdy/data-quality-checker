"""Excel and CSV report writers."""
from __future__ import annotations
from collections import Counter
from io import BytesIO
from datetime import datetime
from pathlib import Path
import pandas as pd
from openpyxl.styles import Font, PatternFill
from .checks.missing import is_missing
from .checks.types import DATE_FORMATS, infer_type, valid_number
from .scoring import column_scores, overall_score

ISSUE_COLUMNS = ["file", "row number", "column", "bad value", "issue type", "explanation"]
SHEET_NAMES = ("Summary", "Column Summary", "Duplicates", "Missing Values", "Type Issues", "Format Issues", "Cross-field & Outliers", "Outlier Reviews", "Recoverable")


def _as_number(value: str) -> float:
    """Parse common decimal and thousands separators."""
    text = value.strip()
    if "," in text and "." in text:
        text = text.replace(",", "") if text.rfind(".") > text.rfind(",") else text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def _as_date(value: str) -> datetime | None:
    """Parse a supported date format for min/max summaries."""
    for fmt in DATE_FORMATS:
        try: return datetime.strptime(value.strip(), fmt)
        except ValueError: pass
    return None


def _column_summary(item: dict, scores: list[dict]) -> list[dict]:
    """Build descriptive statistics and quality score for every source column."""
    frame, name = item["frame"], item["file"]
    config = item.get("config", {})
    by_column = {row["column"]: row for row in scores}
    output = []
    for column in frame.columns:
        values = [str(value) for value in frame[column] if not is_missing(value)]
        kind = str(config.get("types", {}).get(column, infer_type(values))).lower()
        missing_count = len(frame) - len(values)
        record = {"file": name, "column": column, "inferred type": kind, "missing count": missing_count, "missing %": round(missing_count / max(len(frame), 1) * 100, 2), "unique count": len(set(values)), "min": "", "max": "", "top 3 values": "", "weighted issues": by_column[column]["weighted issues"], "quality score": by_column[column]["quality score"]}
        if kind in ("number", "numeric", "integer", "float"):
            numeric = [_as_number(value) for value in values if valid_number(value)]
            if numeric: record["min"], record["max"] = min(numeric), max(numeric)
        elif kind == "date":
            dates = [parsed for value in values if (parsed := _as_date(value)) is not None]
            if dates: record["min"], record["max"] = min(dates).date().isoformat(), max(dates).date().isoformat()
        else:
            top = Counter(values).most_common(3)
            record["top 3 values"] = "; ".join(f"{value} ({count})" for value, count in top)
        output.append(record)
    return output


def build_report(results: list[dict]) -> dict[str, pd.DataFrame]:
    """Combine file results into workbook and CSV report sheets."""
    summaries, column_rows = [], []
    collected = {name: [] for name in SHEET_NAMES[2:]}
    mapping = {"duplicates": "Duplicates", "missing": "Missing Values", "types": "Type Issues", "formats": "Format Issues", "advanced": "Cross-field & Outliers", "outliers": "Outlier Reviews", "recoverable": "Recoverable"}
    for item in results:
        frame, checks = item["frame"], item["checks"]
        config = item.get("config", {})
        counts = {key: len(checks.get(key, pd.DataFrame())) for key in checks}
        if "missing" in checks: counts["missing"] = int(checks["missing"].attrs.get("cell_count", counts["missing"]))
        counts["outliers"] = 0
        counts["recoverable"] = 0
        error_total = sum(counts.get(key, 0) for key in ("duplicates", "missing", "types", "formats", "advanced"))
        recoverable_table = checks.get("recoverable", pd.DataFrame())
        recoverable_count = len(recoverable_table.drop_duplicates(subset=["file", "row number", "column"])) if not recoverable_table.empty else 0
        outlier_count = len(checks.get("outliers", pd.DataFrame()))
        scores = column_scores(frame, checks, config)
        worst = min(scores, key=lambda row: row["quality score"], default={"column": "", "quality score": 100})
        total_weighted = sum(row["weighted issues"] for row in scores)
        optional_columns = config.get("optional_columns", [])
        inferred_rules = checks.get("advanced", pd.DataFrame()).attrs.get("inferred_rules", [])
        inferred_rule_text = "; ".join(f"inferred rule: {rule}" for rule in inferred_rules)
        if not inferred_rule_text:
            inferred_rule_text = "none (configured rules used)" if "rules" in config else "none detected"
        summaries.append({"file name": item["file"], "rows": len(frame), "columns": len(frame.columns), "duplicate issues": counts.get("duplicates", 0), "missing issues": counts.get("missing", 0), "type issues": counts.get("types", 0), "format issues": counts.get("formats", 0), "cross-field issues": counts.get("advanced", 0), "outlier reviews": outlier_count, "recoverable cells": recoverable_count, "total issues": error_total, "quality score": overall_score(frame, checks, config), "worst column": worst["column"], "worst column score": worst["quality score"], "optional columns": ", ".join(optional_columns) if optional_columns else "none set", "inferred rule": inferred_rule_text, "score formula": "max(0, 100 - weighted issues / cells × 100); missing values in optional columns have 25% weight"})
        column_rows.extend(_column_summary(item, scores))
        for key, sheet in mapping.items():
            if key in checks: collected[sheet].append(checks[key])
    output: dict[str, pd.DataFrame] = {"Summary": pd.DataFrame(summaries), "Column Summary": pd.DataFrame(column_rows)}
    for sheet, parts in collected.items():
        if sheet == "Recoverable":
            recoverable_columns = ["file", "row number", "column", "suggested value", "rule used"]
            output[sheet] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=recoverable_columns)
        else:
            output[sheet] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=ISSUE_COLUMNS)
    if len(results) == 1:
        for sheet in SHEET_NAMES[1:]:
            if "file" in output[sheet].columns: output[sheet] = output[sheet].drop(columns="file")
    for sheet in ("Duplicates", "Type Issues", "Format Issues", "Cross-field & Outliers", "Outlier Reviews", "Recoverable"):
        if output[sheet].empty:
            note = {column: "" for column in output[sheet].columns}
            if note: note[output[sheet].columns[0]] = "No issues found"
            output[sheet] = pd.DataFrame([note], columns=output[sheet].columns)
    return output


def write_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Create a styled Excel report as bytes for the dashboard download."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            worksheet = writer.sheets[name]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(fill_type="solid", fgColor="17365D")
            for cells in worksheet.columns:
                width = min(50, max(10, max((len(str(cell.value or "")) for cell in cells), default=0) + 2))
                worksheet.column_dimensions[cells[0].column_letter].width = width
    return output.getvalue()


def write_excel(sheets: dict[str, pd.DataFrame], output: str | Path) -> Path:
    """Write report sheets with readable formatting and frozen headers."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(write_excel_bytes(sheets))
    return path


def write_csv_sheets(sheets: dict[str, pd.DataFrame], output_dir: str | Path) -> list[Path]:
    """Write one CSV per report sheet into the selected folder."""
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, frame in sheets.items():
        path = folder / (name.lower().replace(" ", "_").replace("&", "and") + ".csv")
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        paths.append(path)
    return paths
