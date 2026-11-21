import pandas as pd
from dq_checker.checks import run_checks
from dq_checker.report import build_report

def make_sales_frame():
    rows = []
    for price in range(1, 101):
        total = price * 2
        if price == 1: total += 1  # One bad complete row still meets the 99% rule.
        rows.append({"Total Spent": str(total), "Price Per Unit": str(price), "Quantity": "2"})
    rows.append({"Total Spent": "202", "Price Per Unit": "NA", "Quantity": "2"})
    return pd.DataFrame(rows)

def test_infers_rule_at_99_percent_and_recovers_missing_price():
    frame = make_sales_frame()
    checks = run_checks(frame, "sales.csv")
    assert checks["advanced"].attrs["inferred_rules"] == ["Total Spent = Price Per Unit * Quantity"]
    suggestion = checks["recoverable"].iloc[0]
    assert suggestion["column"] == "Price Per Unit"
    assert suggestion["suggested value"] == 101
    assert frame.loc[100, "Price Per Unit"] == "NA"
    summary = build_report([{"file": "sales.csv", "frame": frame, "checks": checks}])["Summary"].iloc[0]
    assert summary["inferred rule"] == "inferred rule: Total Spent = Price Per Unit * Quantity"

def test_configured_rules_override_inference():
    frame = make_sales_frame()
    checks = run_checks(frame, "sales.csv", config={"rules": ["Quantity = Quantity"]})
    assert checks["advanced"].attrs["inferred_rules"] == []
    assert checks["recoverable"].empty
    summary = build_report([{"file": "sales.csv", "frame": frame, "checks": checks, "config": {"rules": ["Quantity = Quantity"]}}])["Summary"].iloc[0]
    assert summary["inferred rule"] == "none (configured rules used)"
