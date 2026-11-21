import pandas as pd
from dq_checker.checks.missing import check_missing

def test_missing_markers_are_grouped_per_row():
    frame = pd.DataFrame({"a": ["", "ok"], "b": ["NA", "ok"]})
    result = check_missing(frame, "x.csv")
    assert len(result) == 1
    assert result.iloc[0]["column"] == "a, b"
    assert result.iloc[0]["bad value"] == "(empty)"
    assert result.iloc[0]["explanation"] == "2 empty fields"
    assert result.attrs["cell_count"] == 2
    assert result.attrs["summary"][0]["missing %"] == 50.0


def test_empty_field_explanation_uses_singular():
    result = check_missing(pd.DataFrame({"a": ["", "ok"]}), "x.csv")
    assert result.iloc[0]["explanation"] == "1 empty field"
