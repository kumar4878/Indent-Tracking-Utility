from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pandas as pd

from cleaning_engine import is_blank
from header_detector import detect_header_row
from models import HeaderDetectionResult, SheetSnapshot, WorkbookSnapshot


SUPPORTED_PANDAS_ENGINES = {
    ".xlsx": "openpyxl",
    ".xlsm": "openpyxl",
    ".xls": "xlrd",
}


@dataclass(slots=True)
class ReadWorkbookResult:
    workbook: WorkbookSnapshot
    sheet_count: int


def _sheet_rows_from_frame(frame: pd.DataFrame) -> List[List[Any]]:
    normalised = frame.where(pd.notnull(frame), None)
    return [list(row) for row in normalised.itertuples(index=False, name=None)]


def inspect_workbook(file_path: Path, max_probe_rows: int = 25) -> ReadWorkbookResult:
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_PANDAS_ENGINES:
        raise ValueError(f"Unsupported workbook extension: {file_path.suffix}")

    engine = SUPPORTED_PANDAS_ENGINES[suffix]
    sheets = pd.read_excel(file_path, sheet_name=None, header=None, engine=engine)
    snapshots: List[SheetSnapshot] = []

    for sheet_name, frame in sheets.items():
        rows = _sheet_rows_from_frame(frame)
        detection = detect_header_row(rows, max_probe_rows=max_probe_rows)
        snapshots.append(SheetSnapshot(sheet_name=str(sheet_name), rows=rows, header_detection=detection))

    return ReadWorkbookResult(workbook=WorkbookSnapshot(file_path=file_path, sheets=snapshots), sheet_count=len(snapshots))


def build_row_payload(headers: Sequence[str], row_values: Sequence[Any], row_number: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"row_number": row_number}
    mapped: Dict[str, Any] = {}
    for index, header in enumerate(headers):
        value = row_values[index] if index < len(row_values) else None
        if is_blank(value):
            mapped[header] = None
        else:
            mapped[header] = value
    payload["values"] = mapped
    return payload
