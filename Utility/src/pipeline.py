from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from cleaning_engine import hash_payload
from database_service import ReconciliationDatabase
from config_loader import load_json
from excel_reader import build_row_payload, inspect_workbook
from folder_scanner import discover_input_files
from indent_extractor import extract_indent_sheet
from po_extractor import extract_po_sheet
from reconciliation_engine import build_and_store_lifecycle
from rc_extractor import extract_rc_sheet
from tender_extractor import extract_tender_sheet
from models import BatchSummary, RowRecord, SheetRecord


def run_inventory_scan(config: Dict[str, Any], database: ReconciliationDatabase) -> BatchSummary:
    batch_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    config = dict(config)
    config["batch_id"] = batch_id

    discovery = discover_input_files(config)
    batch = BatchSummary(batch_id=batch_id, root_path=str(discovery.root_path), files_discovered=discovery.discovered_count)
    database.begin_batch(batch)

    for file_record in discovery.files:
        existing_file_id = database.file_hash_exists(file_record.file_hash)
        if existing_file_id is not None:
            file_record.status = "duplicate_content"
            file_record.duplicate_of_file_id = existing_file_id
            database.record_file(file_record)
            batch.duplicate_files += 1
            continue

        file_id = database.record_file(file_record)
        batch.files_ingested += 1

        try:
            workbook_result = inspect_workbook(file_record.file_path)
            for sheet_snapshot in workbook_result.workbook.sheets:
                header_row_index = sheet_snapshot.header_detection.row_index if sheet_snapshot.header_detection.row_index is not None else 0
                headers = sheet_snapshot.header_detection.headers or []
                sheet_record = SheetRecord(
                    batch_id=batch_id,
                    file_id=file_id,
                    source_type=file_record.source_type,
                    sheet_name=sheet_snapshot.sheet_name,
                    header_row_index=header_row_index,
                    row_count=len(sheet_snapshot.rows),
                    column_count=max((len(row) for row in sheet_snapshot.rows), default=0),
                    detected_headers=headers,
                    status="ingested",
                )
                sheet_id = database.record_sheet(sheet_record)
                batch.sheets_ingested += 1

                row_records: List[RowRecord] = []
                for row_number, row_values in enumerate(sheet_snapshot.rows, start=1):
                    if row_number - 1 == header_row_index:
                        payload = {"row_number": row_number, "row_kind": "header", "values": row_values}
                        row_kind = "header"
                    elif row_number - 1 > header_row_index and headers:
                        payload = build_row_payload(headers, row_values, row_number)
                        row_kind = "data"
                    else:
                        payload = {"row_number": row_number, "row_kind": "context", "values": row_values}
                        row_kind = "context"
                    row_records.append(
                        RowRecord(
                            batch_id=batch_id,
                            file_id=file_id,
                            sheet_id=sheet_id,
                            source_type=file_record.source_type,
                            sheet_name=sheet_snapshot.sheet_name,
                            row_number=row_number,
                            header_row_index=header_row_index,
                            row_kind=row_kind,
                            row_hash=hash_payload(payload),
                            payload=payload,
                        )
                    )
                batch.rows_ingested += database.record_rows(row_records)

                if file_record.source_type == "Indent":
                    extraction = extract_indent_sheet(
                        batch_id=batch_id,
                        file_id=file_id,
                        sheet_id=sheet_id,
                        source_file=file_record.file_name,
                        source_sheet=sheet_snapshot.sheet_name,
                        sheet_snapshot=sheet_snapshot,
                    )
                    indent_header_id = database.record_indent_header(extraction.header_record)
                    for line_record in extraction.line_records:
                        line_record.indent_header_id = indent_header_id
                    batch.rows_ingested += database.record_indent_lines(extraction.line_records)
                elif file_record.source_type == "RC":
                    extraction = extract_rc_sheet(
                        batch_id=batch_id,
                        file_id=file_id,
                        sheet_id=sheet_id,
                        source_file=file_record.file_name,
                        source_sheet=sheet_snapshot.sheet_name,
                        sheet_snapshot=sheet_snapshot,
                    )
                    batch.rows_ingested += database.record_rc_items(extraction.rc_records)
                elif file_record.source_type == "Tender":
                    extraction = extract_tender_sheet(
                        batch_id=batch_id,
                        file_id=file_id,
                        sheet_id=sheet_id,
                        source_file=file_record.file_name,
                        source_sheet=sheet_snapshot.sheet_name,
                        sheet_snapshot=sheet_snapshot,
                    )
                    batch.rows_ingested += database.record_tender_items(extraction.tender_records)
                elif file_record.source_type == "PO":
                    extraction = extract_po_sheet(
                        batch_id=batch_id,
                        file_id=file_id,
                        sheet_id=sheet_id,
                        source_file=file_record.file_name,
                        source_sheet=sheet_snapshot.sheet_name,
                        sheet_snapshot=sheet_snapshot,
                    )
                    batch.rows_ingested += database.record_po_lines(extraction.po_records)
        except Exception as exc:
            batch.exceptions_created += 1
            database.record_exception(
                batch_id=batch_id,
                exception_code="WORKBOOK_IMPORT_FAILED",
                severity="high",
                status="open",
                summary=f"Failed to import workbook {file_record.file_name}",
                details={"file_path": str(file_record.file_path), "error": str(exc)},
                file_id=file_id,
            )
            continue

    batch.status = "completed" if batch.exceptions_created == 0 else "completed_with_exceptions"
    matching_rules_path = Path(str(config["matching_rules_file"]))
    lifecycle_summary = build_and_store_lifecycle(database, load_json(matching_rules_path))
    batch.rows_ingested += lifecycle_summary.lifecycle_rows
    batch.rows_ingested += lifecycle_summary.allocation_rows
    database.complete_batch(batch)
    return batch
