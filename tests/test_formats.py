import pandas as pd
from dq_checker.checks.formats import check_formats

def test_date_and_number_format_issues():
    df = pd.DataFrame({"date": ["2024-01-01", "01/02/2024", "2024-02-31"], "amount": ["1.25", "1,25", "$3.00"], "qty": ["-1", "2", "3"]})
    result = check_formats(df, "x.csv", {"non_negative": ["qty"]})
    kinds = set(result["issue type"])
    assert {"mixed date format", "invalid date", "mixed number separators", "currency symbol", "negative in non-negative column"}.issubset(kinds)

def test_future_date_is_flagged():
    frame = pd.DataFrame({"date": ["2024-01-01", "2024-01-02", "2035-01-03", "2024-01-04"]})
    result = check_formats(frame, "x.csv")
    assert "future date" in result["issue type"].tolist()
