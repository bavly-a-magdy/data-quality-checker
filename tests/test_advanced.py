import pandas as pd
from dq_checker.checks.advanced import check_categories, check_cross_field, check_outliers, check_recoverable

def test_cross_field_violation_and_recovery():
    frame = pd.DataFrame({"Total Spent": [100, "NA"], "Price Per Unit": [20, 12.5], "Quantity": [4, 4]})
    rule = "Total Spent == Price Per Unit * Quantity"
    result = check_cross_field(frame, "sales.csv", [rule])
    assert "cross-field rule violation" in result["issue type"].tolist()
    recovery = check_recoverable(frame, "sales.csv", [rule]).iloc[0]
    assert recovery["column"] == "Total Spent"
    assert recovery["suggested value"] == 50
    assert recovery["rule used"] == rule
    assert frame.loc[1, "Total Spent"] == "NA"  # Suggestions never change source values.

def test_division_rule_recovers_missing_price():
    frame = pd.DataFrame({"Total Spent": [200], "Price Per Unit": ["NA"], "Quantity": [4]})
    suggestion = check_recoverable(frame, "sales.csv", ["Price Per Unit = Total Spent / Quantity"]).iloc[0]
    assert suggestion["column"] == "Price Per Unit"
    assert suggestion["suggested value"] == 50
    assert suggestion["rule used"] == "Price Per Unit = Total Spent / Quantity"
    assert frame.loc[0, "Price Per Unit"] == "NA"

def test_iqr_outlier_is_review_and_valid_rule_row_is_skipped():
    values = [36, 37, 40, 41, 42, 43, 45, 50, 410]
    prices = [9, 9.25, 10, 10.25, 10.5, 10.75, 11.25, 12.5, 41]
    quantities = [4, 4, 4, 4, 4, 4, 4, 4, 10]
    frame = pd.DataFrame({"Total Spent": values, "Price Per Unit": prices, "Quantity": quantities})
    rule = "Total Spent == Price Per Unit * Quantity"
    assert check_outliers(frame, "sales.csv")["issue type"].eq("review").any()
    assert check_outliers(frame, "sales.csv", [rule]).empty

def test_three_iqr_fence_keeps_moderate_tail_for_review():
    frame = pd.DataFrame({"amount": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 20]})
    reviews = check_outliers(frame, "sales.csv")
    assert "20" not in reviews["bad value"].tolist()

def test_category_variants_are_flagged():
    frame = pd.DataFrame({"Channel": ["Online", "online ", "Store", "Store"]})
    result = check_categories(frame, "sales.csv")
    assert result["issue type"].tolist() == ["inconsistent category", "inconsistent category"]
