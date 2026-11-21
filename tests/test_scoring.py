import pandas as pd
from dq_checker.checks import run_checks
from dq_checker.scoring import column_scores, overall_score, quality_score

def test_score_is_bounded_and_uses_cell_rate():
    assert quality_score(10, 2, 2) == 90.0
    assert quality_score(1, 1, 5) == 0

def test_optional_missing_has_quarter_weight():
    frame = pd.DataFrame({"required": ["x", "x"], "optional": ["NA", "x"]})
    checks = run_checks(frame, "x.csv")
    columns = column_scores(frame, checks, {"optional_columns": ["optional"]})
    optional = next(row for row in columns if row["column"] == "optional")
    assert optional["weighted issues"] == .25
    assert optional["quality score"] == 87.5
    assert overall_score(frame, checks, {"optional_columns": ["optional"]}) == 93.75


def test_recoverable_suggestion_does_not_add_score_penalty():
    frame = pd.DataFrame({"Total Spent": ["NA"], "Price Per Unit": [12.5], "Quantity": [4]})
    config = {"rules": ["Total Spent == Price Per Unit * Quantity"]}
    checks = run_checks(frame, "x.csv", config=config)
    from dq_checker.report import build_report
    report = build_report([{"file": "x.csv", "frame": frame, "checks": checks, "config": config}])
    assert len(report["Recoverable"]) == 1
    assert report["Summary"].iloc[0]["recoverable cells"] == 1
    assert report["Summary"].iloc[0]["total issues"] == 1  # missing cell only


def test_outlier_reviews_do_not_reduce_quality_score():
    frame = pd.DataFrame({"amount": [10, 11, 12, 13, 14, 15, 16, 18, 999]})
    checks = run_checks(frame, "x.csv")
    assert len(checks["outliers"]) == 1
    assert checks["outliers"].iloc[0]["issue type"] == "review"
    assert overall_score(frame, checks) == 100.0

def test_summary_shows_optional_columns_and_separate_review_count():
    frame = pd.DataFrame({"amount": [10, 11, 12, 13, 14, 15, 16, 18, 999], "extra": ["NA"] + ["x"] * 8})
    config = {"optional_columns": ["extra"]}
    checks = run_checks(frame, "x.csv", config=config)
    from dq_checker.report import build_report
    report = build_report([{"file": "x.csv", "frame": frame, "checks": checks, "config": config}])
    summary = report["Summary"].iloc[0]
    assert summary["optional columns"] == "extra"
    assert summary["outlier reviews"] == 1
    assert summary["total issues"] == 1  # Optional missing cell is still listed, with a quarter score weight.
    assert summary["quality score"] == 98.61
    assert len(report["Outlier Reviews"]) == 1
