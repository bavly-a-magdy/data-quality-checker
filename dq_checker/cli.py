"""Command line entry point."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .reader import read_csv_file, DataReadError
from .checks import run_checks
from .report import build_report, write_excel, write_csv_sheets
def main(argv: list[str] | None = None) -> int:
    """Run checks for CSV file(s) and export a report."""
    parser=argparse.ArgumentParser(description="Find common data quality problems in CSV files.")
    parser.add_argument("input",help="CSV file or folder containing CSV files"); parser.add_argument("--output",default="reports/report.xlsx",help="Excel path or CSV output folder"); parser.add_argument("--format",choices=("excel","csv"),default="excel"); parser.add_argument("--key-columns",help="Comma-separated duplicate key columns"); parser.add_argument("--config",help="Optional JSON config with types and non_negative")
    args=parser.parse_args(argv); source=Path(args.input); files=sorted(source.glob("*.csv")) if source.is_dir() else [source]
    if not files: print(f"No CSV files found: {source}",file=sys.stderr); return 2
    try: config=json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
    except (OSError,json.JSONDecodeError) as exc: print(f"Invalid config: {exc}",file=sys.stderr); return 2
    keys=[x.strip() for x in args.key_columns.split(",") if x.strip()] if args.key_columns else None; results=[]; failed=False
    for path in files:
        try:
            frame=read_csv_file(path); missing=set(keys or [])-set(frame.columns)
            if missing: raise DataReadError(f"{path.name}: key columns not found: {', '.join(sorted(missing))}")
            results.append({"file":path.name,"frame":frame,"checks":run_checks(frame,path.name,keys,config),"config":config})
        except (DataReadError,OSError) as exc: print(str(exc),file=sys.stderr); failed=True
    if not results: return 2
    sheets=build_report(results)
    if args.format=="csv": paths=write_csv_sheets(sheets,args.output); print(f"Wrote {len(paths)} report CSVs to {args.output}")
    else: path=write_excel(sheets,args.output); print(f"Wrote report: {path}")
    return 1 if failed else 0
