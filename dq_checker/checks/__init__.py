"""Reusable data quality checks."""
from __future__ import annotations
import pandas as pd
from .advanced import check_categories, check_cross_field, check_outliers, check_recoverable, infer_arithmetic_rules
from .duplicates import check_duplicates
from .formats import check_formats
from .missing import check_missing
from .types import check_types

def run_checks(frame: pd.DataFrame, file_name: str, key_columns: list[str] | None = None, config: dict | None = None) -> dict[str, pd.DataFrame]:
    """Run configured or inferred rules and return normalized issue tables."""
    config = config or {}
    if "rules" in config:
        rules = list(config.get("rules") or [])
        inferred_rules: list[str] = []
    else:
        inferred_rules = infer_arithmetic_rules(frame)
        rules = inferred_rules
    advanced = pd.concat([
        check_cross_field(frame, file_name, rules),
        check_categories(frame, file_name),
    ], ignore_index=True)
    advanced.attrs["inferred_rules"] = inferred_rules
    return {
        "duplicates": check_duplicates(frame, file_name, key_columns),
        "missing": check_missing(frame, file_name),
        "types": check_types(frame, file_name, config.get("types", {})),
        "formats": check_formats(frame, file_name, config),
        "advanced": advanced,
        "outliers": check_outliers(frame, file_name, rules),
        "recoverable": check_recoverable(frame, file_name, rules),
    }
