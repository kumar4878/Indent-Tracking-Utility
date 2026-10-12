from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence

from cleaning_engine import is_blank, normalize_whitespace
from models import PORowRecord, SheetSnapshot


PO_HEADER_MARKERS = ["po.", "itemname", "hospital/"]


@dataclass(slots=True)
class POExtractionResult:
    po_records: List[PORowRecord]


def _safe_cell(row: Sequence[Any], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return normalize_whitespace(row[index])


def _find_header_row(rows: Sequence[Sequence[Any]]) -> int:
    for row_index, row in enumerate(rows):
        joined = " | ".join(normalize_whitespace(value).lower() for value in row if not is_blank(value))
        if all(marker in joined for marker in PO_HEADER_MARKERS):
            return row_index
    return 0


def extract_po_sheet(
    *,
    batch_id: str,
    file_id: int,
    sheet_id: int,
    source_file: str,
    source_sheet: str,
    sheet_snapshot: SheetSnapshot,
) -> POExtractionResult:
    rows = sheet_snapshot.rows
    header_row_index = _find_header_row(rows)
    po_records: List[PORowRecord] = []

    for row_number, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
        po_no = _safe_cell(row, 1)
        source_item_name = _safe_cell(row, 6)
        if is_blank(po_no) and is_blank(source_item_name):
            continue

        po_records.append(
            PORowRecord(
                batch_id=batch_id,
                file_id=file_id,
                sheet_id=sheet_id,
                source_file=source_file,
                source_sheet=source_sheet,
                source_row=row_number,
                po_no=po_no,
                po_date=_safe_cell(row, 3),
                gross_amount=_safe_cell(row, 4),
                vendor_name=_safe_cell(row, 5),
                source_item_name=source_item_name,
                ordered_qty=_safe_cell(row, 7),
                unit_rate_incl_gst=_safe_cell(row, 8),
                total_amount=_safe_cell(row, 9),
                institution_type=_safe_cell(row, 10),
                location=_safe_cell(row, 11),
                district=_safe_cell(row, 12),
                scheme=_safe_cell(row, 13),
                hod=_safe_cell(row, 14),
                budget=_safe_cell(row, 15),
                delivery_period=_safe_cell(row, 16),
                case_worker_name=_safe_cell(row, 17),
                remarks=_safe_cell(row, 18),
                agt_no=_safe_cell(row, 19),
                agt_date=_safe_cell(row, 20),
                make=_safe_cell(row, 21),
                model=_safe_cell(row, 22),
                tender_no=_safe_cell(row, 23),
                tender_date=_safe_cell(row, 24),
                bfc_date=_safe_cell(row, 25),
                equip_fun=_safe_cell(row, 26),
                raw_payload={"row": row},
            )
        )

    return POExtractionResult(po_records=po_records)
