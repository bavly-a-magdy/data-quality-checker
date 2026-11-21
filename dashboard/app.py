"""Readable Streamlit dashboard for data quality reports."""
from __future__ import annotations
import inspect
import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
import pandas as pd
import plotly.express as px
import streamlit as st
from dq_checker.checks import run_checks
from dq_checker.reader import DataReadError, read_csv_bytes
from dq_checker.report import build_report, write_excel_bytes

st.set_page_config(page_title="Data Quality Checker", page_icon="🔎", layout="wide")
st.title("Data Quality Checker")
st.caption("Find and understand CSV issues without changing your source data.")

def _stretch_width(widget) -> dict:
    """Use the current width API while supporting older Streamlit versions."""
    try:
        parameters = inspect.signature(widget).parameters
    except (TypeError, ValueError):
        parameters = {}
    return {"width": "stretch"} if "width" in parameters else {"use_container_width": True}

with st.sidebar:
    st.header("Check your files")
    uploads = st.file_uploader("CSV files", type=["csv"], accept_multiple_files=True)
    keys_text = st.text_input("Duplicate key columns (optional)", placeholder="Order ID, Customer ID")
    config_upload = st.file_uploader("Rules and type overrides (optional JSON)", type=["json"])
    run = st.button("Run checks", type="primary", **_stretch_width(st.button))
    st.caption("Key columns find duplicate records even when other values differ.")

if run:
    st.session_state.pop("dq_results", None)
    if not uploads:
        st.error("Choose at least one CSV file, then run checks.")
    else:
        try:
            config = json.loads(config_upload.getvalue().decode("utf-8")) if config_upload else {}
            if not isinstance(config, dict): raise ValueError("The config must be a JSON object.")
            keys = [value.strip() for value in keys_text.split(",") if value.strip()] or None
            found = []
            for upload in uploads:
                try:
                    frame = read_csv_bytes(upload.getvalue(), upload.name)
                    missing_keys = set(keys or []) - set(frame.columns)
                    if missing_keys: raise DataReadError(f"{upload.name}: key columns not found: {', '.join(sorted(missing_keys))}")
                    found.append({"file": upload.name, "frame": frame, "checks": run_checks(frame, upload.name, keys, config), "config": config})
                except (DataReadError, UnicodeError) as exc: st.error(str(exc))
            if found: st.session_state["dq_results"] = found
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc: st.error(f"Could not read the config: {exc}")

results = st.session_state.get("dq_results", [])
if not results:
    st.info("Upload CSV files in the sidebar and select **Run checks** to see the results.")
else:
    sheets = build_report(results)
    summary = sheets["Summary"]
    rows = int(summary["rows"].sum())
    columns = int(summary["columns"].sum())
    issue_count = int(summary["total issues"].sum())
    duplicates = sum(len(item["checks"]["duplicates"]) for item in results)
    recoverable_cells = sum(len(item["checks"]["recoverable"].drop_duplicates(subset=["file", "row number", "column"])) for item in results)
    outlier_reviews = sum(len(item["checks"]["outliers"]) for item in results)
    missing_cells = sum(int(item["checks"]["missing"].attrs.get("cell_count", 0)) for item in results)
    cell_count = sum(len(item["frame"]) * len(item["frame"].columns) for item in results)
    missing_pct = round(missing_cells / max(cell_count, 1) * 100, 2)
    score = round(float(summary["quality score"].mean()), 1)
    worst_index = summary["worst column score"].idxmin()
    worst_column = str(summary.loc[worst_index, "worst column"])
    worst_score = float(summary.loc[worst_index, "worst column score"])

    st.subheader("At a glance")
    first_row = st.columns(4)
    for card, label, value, help_text in zip(first_row, ["Rows checked", "Columns", "Issues found", "Duplicate rows"], [f"{rows:,}", f"{columns:,}", f"{issue_count:,}", f"{duplicates:,}"], ["Rows across uploaded files.", "Columns across uploaded files.", "Scored findings; review items are separate.", "Rows involved in duplicate findings."]):
        card.metric(label, value, help=help_text)
    second_row = st.columns(3)
    for card, label, value, help_text in zip(second_row, ["Recoverable cells", "Outlier reviews", "Quality score /100"], [f"{recoverable_cells:,}", f"{outlier_reviews:,}", f"{score:.1f}"], ["Suggestions only; source files are never changed.", "Values beyond the 3 × IQR fence, shown separately and not scored.", f"Lowest scoring column: {worst_column} ({worst_score:.1f}/100). Optional missing values carry 25% weight."]):
        card.metric(label, value, help=help_text)
    st.caption(f"Missing cells: {missing_cells:,} of {cell_count:,} ({missing_pct}%). Lowest scoring column: **{worst_column}** ({worst_score:.1f}/100).")
    inferred_rules = [rule for item in results for rule in item["checks"]["advanced"].attrs.get("inferred_rules", [])]
    if inferred_rules:
        st.caption("Inferred rule(s): " + "; ".join(inferred_rules))

    detail_tables = [item["checks"][key] for item in results for key in ("duplicates", "missing", "types", "formats", "advanced") if len(item["checks"][key])]
    issues = pd.concat(detail_tables, ignore_index=True) if detail_tables else pd.DataFrame(columns=["file", "row number", "column", "bad value", "issue type", "explanation"])
    st.subheader("Issue overview")
    chart_left, chart_right = st.columns(2)
    issue_types = issues.groupby("issue type").size().reset_index(name="Findings") if len(issues) else pd.DataFrame()
    with chart_left:
        if len(issue_types) > 1:
            chart_data = issue_types.sort_values("Findings")
            chart = px.bar(chart_data, x="Findings", y="issue type", orientation="h", text="Findings", title="Findings by type", template="plotly_white")
            chart.update_layout(height=max(260, 42 * len(chart_data)), margin=dict(l=8, r=18, t=48, b=8), yaxis_title="", xaxis_title="Finding rows")
            chart.update_traces(textposition="outside", cliponaxis=False, marker_color="#2563EB")
            st.plotly_chart(chart, **_stretch_width(st.plotly_chart))
        elif len(issue_types) == 1:
            st.info(f"All {int(issue_types.iloc[0]['Findings']):,} findings are **{issue_types.iloc[0]['issue type']}**.")
        else:
            st.success("No issues found.")
    with chart_right:
        if len(issues):
            issue_counts_by_column: dict[str, int] = {}
            for value in issues["column"].dropna().astype(str):
                for column_name in [part.strip() for part in value.split(",") if part.strip()]:
                    issue_counts_by_column[column_name] = issue_counts_by_column.get(column_name, 0) + 1
            missing_counts_by_column: dict[str, int] = {}
            for item in results:
                for missing_row in item["checks"]["missing"].attrs.get("summary", []):
                    missing_counts_by_column[missing_row["column"]] = missing_counts_by_column.get(missing_row["column"], 0) + int(missing_row["missing count"])
            column_data = pd.DataFrame([{"column": name, "finding count": count, "missing cells": missing_counts_by_column.get(name, 0)} for name, count in issue_counts_by_column.items()])
            column_data["% of findings"] = (column_data["finding count"] / max(column_data["finding count"].sum(), 1) * 100).round(1)
            column_data = column_data.sort_values("% of findings").tail(20)
            chart = px.bar(column_data, x="% of findings", y="column", orientation="h", text="% of findings", title="Issues by column", template="plotly_white", hover_data={"finding count": True, "missing cells": True, "% of findings": ":.1f"})
            chart.update_layout(height=max(300, 29 * len(column_data)), margin=dict(l=8, r=30, t=48, b=8), yaxis_title="", xaxis_title="Share of all findings (%)")
            chart.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False, marker_color="#2563EB")
            st.plotly_chart(chart, **_stretch_width(st.plotly_chart))
        else:
            st.info("No column issues to chart.")

    if len(results) > 1:
        st.subheader("File comparison")
        st.dataframe(summary[["file name", "rows", "columns", "total issues", "quality score", "worst column"]], hide_index=True, **_stretch_width(st.dataframe))

    st.subheader("Explore findings")
    issue_tabs = st.tabs(["All issues", "Duplicates", "Missing values", "Type issues", "Format issues", "Cross-field & categories", "Outlier reviews", "Recoverable", "Column Summary"])
    tab_tables = [
        ("All issues", issues), ("Duplicates", sheets["Duplicates"]), ("Missing values", sheets["Missing Values"]),
        ("Type issues", sheets["Type Issues"]), ("Format issues", sheets["Format Issues"]),
        ("Cross-field & categories", sheets["Cross-field & Outliers"]), ("Outlier reviews", sheets["Outlier Reviews"]),
        ("Recoverable", sheets["Recoverable"]), ("Column Summary", sheets["Column Summary"]),
    ]
    for tab, (tab_name, table) in zip(issue_tabs, tab_tables):
        with tab:
            has_empty_note = not table.empty and table.astype(str).apply(lambda column: column.eq("No issues found")).any().any()
            if table.empty or has_empty_note:
                st.success("No findings in this category.")
                continue
            if tab_name == "Column Summary":
                summary_view = table.copy()
                for numeric_range in ("min", "max"):
                    if numeric_range in summary_view:
                        summary_view[numeric_range] = summary_view[numeric_range].map(lambda value: "" if pd.isna(value) else str(value))
                st.dataframe(summary_view, hide_index=True, height=420, **_stretch_width(st.dataframe))
                continue
            if tab_name == "Recoverable":
                st.caption("These are suggestions only. The uploaded CSV is never changed.")
                st.dataframe(table, hide_index=True, **_stretch_width(st.dataframe))
                continue
            filtered = table.copy()
            filters = st.columns(3)
            file_values = sorted(filtered["file"].dropna().unique().tolist()) if "file" in filtered else []
            column_values = sorted({part.strip() for value in filtered["column"].dropna().astype(str) for part in value.split(",")})
            type_values = sorted(filtered["issue type"].dropna().unique().tolist()) if "issue type" in filtered else []
            selected_file = filters[0].selectbox("File filter", ["All files", *file_values], key=f"file_{tab_name}") if file_values else "All files"
            selected_column = filters[1].selectbox("Column filter", ["All columns", *column_values], key=f"column_{tab_name}")
            selected_type = filters[2].selectbox("Issue filter", ["All issue types", *type_values], key=f"issue_{tab_name}")
            if selected_file != "All files" and "file" in filtered: filtered = filtered[filtered["file"] == selected_file]
            if selected_column != "All columns": filtered = filtered[filtered["column"].astype(str).apply(lambda value: selected_column in [part.strip() for part in value.split(",")])]
            if selected_type != "All issue types" and "issue type" in filtered: filtered = filtered[filtered["issue type"] == selected_type]
            search = st.text_input("Search values or explanations", key=f"search_{tab_name}", placeholder="Search values, row numbers, or details")
            if search:
                match = filtered.astype(str).apply(lambda series: series.str.contains(search, case=False, regex=False)).any(axis=1)
                filtered = filtered[match]
            st.caption(f"{len(filtered):,} finding rows match these filters.")
            if "issue type" in filtered:
                grouped = filtered.copy()
                grouped["example"] = grouped["bad value"].astype(str).str.slice(0, 70)
                grouped["column"] = grouped["column"].fillna("").astype(str).str.split(",")
                grouped = grouped.explode("column")
                grouped["column"] = grouped["column"].str.strip()
                overview = grouped.groupby("column", as_index=False).agg(issue_count=("issue type", "size"), examples=("example", lambda values: " | ".join(values.drop_duplicates().head(3))))
                overview["% of findings"] = (overview["issue_count"] / max(overview["issue_count"].sum(), 1) * 100).round(1)
                st.dataframe(overview.sort_values("issue_count", ascending=False), hide_index=True, **_stretch_width(st.dataframe))
                with st.expander("View affected rows and details", expanded=False):
                    detail = filtered.drop(columns=["explanation"], errors="ignore")
                    detail = detail.rename(columns={"file": "File", "row number": "Row", "column": "Column", "bad value": "Value found", "issue type": "Issue"})
                    st.dataframe(detail, hide_index=True, height=420, column_config={"Row": st.column_config.NumberColumn("CSV row", help="Counts the header as row 1."), "Value found": st.column_config.TextColumn("Value found", width="large")}, **_stretch_width(st.dataframe))
                    explanation_options = filtered[["issue type", "explanation"]].drop_duplicates()
                    st.markdown("**What the findings mean**")
                    for _, explanation in explanation_options.iterrows(): st.markdown(f"- **{explanation['issue type']}:** {explanation['explanation']}")

    st.subheader("Download reports")
    excel_data = write_excel_bytes(sheets)
    csv_archive = BytesIO()
    with ZipFile(csv_archive, "w", ZIP_DEFLATED) as archive:
        for name, frame in sheets.items(): archive.writestr(name.lower().replace(" ", "_").replace("&", "and") + ".csv", frame.to_csv(index=False))
    download_excel, download_csv = st.columns(2)
    download_excel.download_button("Download Excel report", excel_data, "data_quality_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **_stretch_width(download_excel.download_button))
    download_csv.download_button("Download CSV report (all sheets)", csv_archive.getvalue(), "data_quality_report_csv.zip", "application/zip", **_stretch_width(download_csv.download_button))
