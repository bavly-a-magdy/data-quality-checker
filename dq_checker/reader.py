"""CSV reading helpers that preserve source values as text."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
import pandas as pd

class DataReadError(ValueError):
    """Raised when a CSV cannot be read safely."""

def read_csv_bytes(data: bytes, name: str = "upload.csv") -> pd.DataFrame:
    """Read CSV bytes with encoding and delimiter checks."""
    if not data:
        raise DataReadError(f"{name}: file is empty")
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            frame = pd.read_csv(BytesIO(data), dtype=str, keep_default_na=False, encoding=encoding)
            if len(frame.columns) <= 1 and any(d in data.decode(encoding, errors="replace") for d in (";", "\t", "|")):
                raise DataReadError(f"{name}: wrong delimiter; expected comma-separated values")
            if len(frame.columns) == 0:
                raise DataReadError(f"{name}: no columns found")
            frame.attrs["source_name"] = name
            return frame
        except UnicodeDecodeError as exc:
            last_error = exc
        except pd.errors.EmptyDataError as exc:
            raise DataReadError(f"{name}: file has no data") from exc
        except pd.errors.ParserError as exc:
            raise DataReadError(f"{name}: CSV structure is invalid: {exc}") from exc
    raise DataReadError(f"{name}: could not decode CSV: {last_error}")

def read_csv_file(path: str | Path) -> pd.DataFrame:
    """Read a CSV file without converting source values."""
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise DataReadError(f"File not found: {source}")
    try:
        return read_csv_bytes(source.read_bytes(), source.name)
    except OSError as exc:
        raise DataReadError(f"Could not read {source}: {exc}") from exc
