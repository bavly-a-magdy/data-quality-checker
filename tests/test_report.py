import pandas as pd
from openpyxl import load_workbook
from dq_checker.checks import run_checks
from dq_checker.report import build_report, write_excel

def test_column_summary_and_excel_styles(tmp_path):
    frame = pd.DataFrame({"name": ["Ada", "Ada", "NA"], "amount": ["3", "5", "7"]})
    result = {"file": "one.csv", "frame": frame, "checks": run_checks(frame, "one.csv")}
    sheets = build_report([result])
    assert "Column Summary" in sheets
    assert "file" not in sheets["Missing Values"].columns
    assert "file" not in sheets["Column Summary"].columns
    assert sheets["Duplicates"].iloc[0, 0] == "No issues found"
    assert sheets["Type Issues"].iloc[0, 0] == "No issues found"
    assert sheets["Format Issues"].iloc[0, 0] == "No issues found"
    assert sheets["Cross-field & Outliers"].iloc[0, 0] == "No issues found"
    assert sheets["Outlier Reviews"].iloc[0, 0] == "No issues found"
    assert sheets["Recoverable"].iloc[0, 0] == "No issues found"
    assert sheets["Summary"].iloc[0]["optional columns"] == "none set"
    path = write_excel(sheets, tmp_path / "report.xlsx")
    book = load_workbook(path)
    for sheet in book.worksheets:
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref
        assert sheet[1][0].font.bold
        assert sheet[1][0].font.color.rgb.endswith("FFFFFF")
        assert all(column.width <= 50 for column in sheet.column_dimensions.values())
