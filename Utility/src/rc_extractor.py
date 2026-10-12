from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from cleaning_engine import is_blank, normalize_whitespace, safe_text
from models import RCRecord, SheetSnapshot


RC_HEADER_KEYWORDS = ["name of the item", "name of the firm", "rank", "unit rate inclusive of gst"]


@dataclass(slots=True)
class RCExtractionResult:
    rc_records: List[RCRecord]


def _safe_cell(row: Sequence[Any], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return normalize_whitespace(row[index])


def _find_header_row(rows: Sequence[Sequence[Any]]) -> int:
    for row_index, row in enumerate(rows):
        joined = " | ".join(normalize_whitespace(value).lower() for value in row if not is_blank(value))
        if all(keyword in joined for keyword in RC_HEADER_KEYWORDS[:2]):
            return row_index
    return 0


def _carry_forward_value(current: str, candidate: str) -> str:
    return candidate if not is_blank(candidate) else current


def extract_rc_sheet(
    *,
    batch_id: str,
    file_id: int,
    sheet_id: int,
    source_file: str,
    source_sheet: str,
    sheet_snapshot: SheetSnapshot,
) -> RCExtractionResult:
    rows = sheet_snapshot.rows
    header_row_index = _find_header_row(rows)
    rc_records: List[RCRecord] = []
    current_group = ""
    current_item_name = ""

    for row_number, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
        source_item_name = _safe_cell(row, 1)
        vendor_name = _safe_cell(row, 2)
        if not is_blank(source_item_name):
            current_item_name = source_item_name
            current_group = _safe_cell(row, 0)
        elif is_blank(vendor_name):
            continue

        if is_blank(current_item_name) and is_blank(vendor_name):
            continue

        rc_records.append(
            RCRecord(
                batch_id=batch_id,
                file_id=file_id,
                sheet_id=sheet_id,
                source_file=source_file,
                source_sheet=source_sheet,
                source_row=row_number,
                rc_group_no=current_group,
                source_item_name=current_item_name,
                vendor_name=vendor_name,
                rank=_safe_cell(row, 3),
                make=_safe_cell(row, 4),
                model=_safe_cell(row, 5),
                basic_rate=_safe_cell(row, 6),
                gst_percent=_safe_cell(row, 7),
                unit_rate_incl_gst=_safe_cell(row, 9),
                bfc_date=_safe_cell(row, 11),
                rc_valid_upto=_safe_cell(row, 12),
                tender_quantity=_safe_cell(row, 13),
                remarks=_safe_cell(row, 14),
                department=_safe_cell(row, 15),
                raw_payload={"row": row},
            )
        )

    return RCExtractionResult(rc_records=rc_records)
