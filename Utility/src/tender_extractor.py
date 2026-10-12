from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence

from cleaning_engine import is_blank, normalize_whitespace
from models import SheetSnapshot, TenderRecord


TENDER_HEADER_MARKERS = ["tender number", "description of tender", "tender stage"]


@dataclass(slots=True)
class TenderExtractionResult:
    tender_records: List[TenderRecord]


def _safe_cell(row: Sequence[Any], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return normalize_whitespace(row[index])


def _find_header_row(rows: Sequence[Sequence[Any]]) -> int:
    for row_index, row in enumerate(rows):
        joined = " | ".join(normalize_whitespace(value).lower() for value in row if not is_blank(value))
        if all(marker in joined for marker in TENDER_HEADER_MARKERS):
            return row_index
    return 0


def extract_tender_sheet(
    *,
    batch_id: str,
    file_id: int,
    sheet_id: int,
    source_file: str,
    source_sheet: str,
    sheet_snapshot: SheetSnapshot,
) -> TenderExtractionResult:
    rows = sheet_snapshot.rows
    header_row_index = _find_header_row(rows)
    tender_records: List[TenderRecord] = []
    current_tender_no = ""
    current_description = ""
    current_bid_start = ""
    current_pre_bid = ""
    current_bid_close = ""
    current_case_worker = ""
    current_tender_stage = ""

    for row_number, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
        tender_no = _safe_cell(row, 1)
        description = _safe_cell(row, 2)
        item_name = _safe_cell(row, 3)
        if not is_blank(tender_no):
            current_tender_no = tender_no
        if not is_blank(description):
            current_description = description
        if not is_blank(_safe_cell(row, 6)):
            current_bid_start = _safe_cell(row, 6)
        if not is_blank(_safe_cell(row, 7)):
            current_pre_bid = _safe_cell(row, 7)
        if not is_blank(_safe_cell(row, 8)):
            current_bid_close = _safe_cell(row, 8)
        if not is_blank(_safe_cell(row, 9)):
            current_tender_stage = _safe_cell(row, 9)
        if not is_blank(_safe_cell(row, 10)):
            current_case_worker = _safe_cell(row, 10)

        if is_blank(item_name) and is_blank(current_tender_no):
            continue
        if is_blank(item_name):
            continue

        tender_records.append(
            TenderRecord(
                batch_id=batch_id,
                file_id=file_id,
                sheet_id=sheet_id,
                source_file=source_file,
                source_sheet=source_sheet,
                source_row=row_number,
                tender_no=current_tender_no,
                source_item_name=item_name,
                tender_description=current_description,
                qty=_safe_cell(row, 4),
                no_of_responses=_safe_cell(row, 5),
                bid_start_date=current_bid_start,
                pre_bid_date=current_pre_bid,
                bid_close_date=current_bid_close,
                tender_stage=current_tender_stage,
                case_worker=current_case_worker,
                raw_payload={"row": row},
            )
        )

    return TenderExtractionResult(tender_records=tender_records)
