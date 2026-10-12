from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Sequence, Tuple

from cleaning_engine import is_blank, normalize_whitespace, safe_text
from models import IndentHeaderRecord, IndentLineRecord, SheetSnapshot


DISTRICT_RE = re.compile(r"\bDistrict\b", re.IGNORECASE)


@dataclass(slots=True)
class IndentExtractionResult:
    header_record: IndentHeaderRecord
    line_records: List[IndentLineRecord]


def _safe_cell(row: Sequence[Any], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return normalize_whitespace(row[index])


def _infer_institution_parts(value: str) -> Tuple[str, str]:
    text = normalize_whitespace(value)
    if not text:
        return "", ""
    district = ""
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if parts:
            district_candidate = parts[-1]
            district_candidate = re.sub(r"\(.*?\)", "", district_candidate)
            district_candidate = DISTRICT_RE.sub("", district_candidate)
            district_candidate = normalize_whitespace(district_candidate).strip(" ,-()")
            district = district_candidate
            institution_name = ", ".join(parts[:-1]).strip()
            return institution_name, district
    return text, district


def _derive_normalized_item_name(item_name: str) -> str:
    return normalize_whitespace(item_name)


def extract_indent_sheet(
    *,
    batch_id: str,
    file_id: int,
    sheet_id: int,
    source_file: str,
    source_sheet: str,
    sheet_snapshot: SheetSnapshot,
) -> IndentExtractionResult:
    rows = sheet_snapshot.rows
    header_row_index = sheet_snapshot.header_detection.row_index or 1
    metadata_row_index = min(header_row_index + 1, len(rows) - 1)

    header_row = rows[header_row_index] if header_row_index < len(rows) else []
    metadata_row = rows[metadata_row_index] if metadata_row_index < len(rows) else []

    institution_text = _safe_cell(metadata_row, 1)
    institution_name, district = _infer_institution_parts(institution_text)
    source_title = _safe_cell(rows, 0) if rows else ""

    header_record = IndentHeaderRecord(
        batch_id=batch_id,
        file_id=file_id,
        sheet_id=sheet_id,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=metadata_row_index + 1,
        indent_no=_safe_cell(metadata_row, 9),
        indent_date=_safe_cell(metadata_row, 8),
        institution_text=institution_text,
        institution_name=institution_name,
        district=district,
        as_number=_safe_cell(metadata_row, 2),
        as_amount=_safe_cell(metadata_row, 3),
        budget_head=_safe_cell(metadata_row, 4),
        department=_safe_cell(metadata_row, 5),
        source_title=safe_text(rows[0][0]) if rows and rows[0] else "",
        raw_payload={
            "header_row": header_row,
            "metadata_row": metadata_row,
        },
    )

    line_records: List[IndentLineRecord] = []
    for row_number, row in enumerate(rows[metadata_row_index + 1 :], start=metadata_row_index + 2):
        source_serial_no = _safe_cell(row, 0)
        department = _safe_cell(row, 5)
        source_item_name = _safe_cell(row, 6)
        required_qty = _safe_cell(row, 7)
        if is_blank(source_serial_no) and is_blank(source_item_name) and is_blank(required_qty):
            continue
        line_records.append(
            IndentLineRecord(
                batch_id=batch_id,
                file_id=file_id,
                sheet_id=sheet_id,
                indent_header_id=None,
                source_file=source_file,
                source_sheet=source_sheet,
                source_row=row_number,
                source_serial_no=source_serial_no,
                department=department,
                source_item_name=source_item_name,
                normalized_item_name=_derive_normalized_item_name(source_item_name),
                required_qty=required_qty,
                unit_of_measure="",
                raw_payload={"row": row},
            )
        )

    return IndentExtractionResult(header_record=header_record, line_records=line_records)