from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from cleaning_engine import json_dumps
from models import BatchSummary, FileRecord, IndentHeaderRecord, IndentLineRecord, LifecycleRecord, POAllocationRecord, PORowRecord, RCRecord, RowRecord, SheetRecord, TenderRecord


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS run_batches (
    batch_id TEXT PRIMARY KEY,
    root_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    files_discovered INTEGER NOT NULL DEFAULT 0,
    files_ingested INTEGER NOT NULL DEFAULT 0,
    duplicate_files INTEGER NOT NULL DEFAULT 0,
    sheets_ingested INTEGER NOT NULL DEFAULT 0,
    rows_ingested INTEGER NOT NULL DEFAULT 0,
    exceptions_created INTEGER NOT NULL DEFAULT 0,
    output_path TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS source_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    folder_name TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    modified_at TEXT NOT NULL,
    import_status TEXT NOT NULL,
    duplicate_of_file_id INTEGER,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_files_hash ON source_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_source_files_batch ON source_files(batch_id);

CREATE TABLE IF NOT EXISTS source_sheets (
    sheet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    batch_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    header_row_index INTEGER,
    row_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    detected_headers_json TEXT NOT NULL,
    import_status TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES source_files(file_id)
);

CREATE INDEX IF NOT EXISTS idx_source_sheets_batch ON source_sheets(batch_id);

CREATE TABLE IF NOT EXISTS source_rows (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    sheet_id INTEGER NOT NULL,
    batch_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    header_row_index INTEGER,
    row_kind TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES source_files(file_id),
    FOREIGN KEY(sheet_id) REFERENCES source_sheets(sheet_id)
);

CREATE INDEX IF NOT EXISTS idx_source_rows_batch ON source_rows(batch_id);
CREATE INDEX IF NOT EXISTS idx_source_rows_file_sheet ON source_rows(file_id, sheet_id);

CREATE TABLE IF NOT EXISTS indent_headers (
    indent_header_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    sheet_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    indent_no TEXT,
    indent_date TEXT,
    institution_text TEXT,
    institution_name TEXT,
    district TEXT,
    as_number TEXT,
    as_amount TEXT,
    budget_head TEXT,
    department TEXT,
    source_title TEXT,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES source_files(file_id),
    FOREIGN KEY(sheet_id) REFERENCES source_sheets(sheet_id)
);

CREATE INDEX IF NOT EXISTS idx_indent_headers_batch ON indent_headers(batch_id);

CREATE TABLE IF NOT EXISTS indent_lines (
    indent_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    sheet_id INTEGER NOT NULL,
    indent_header_id INTEGER,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    source_serial_no TEXT,
    department TEXT,
    source_item_name TEXT,
    normalized_item_name TEXT,
    required_qty TEXT,
    unit_of_measure TEXT,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES source_files(file_id),
    FOREIGN KEY(sheet_id) REFERENCES source_sheets(sheet_id),
    FOREIGN KEY(indent_header_id) REFERENCES indent_headers(indent_header_id)
);

CREATE INDEX IF NOT EXISTS idx_indent_lines_batch ON indent_lines(batch_id);

CREATE TABLE IF NOT EXISTS rc_items (
    rc_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    sheet_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    rc_group_no TEXT,
    source_item_name TEXT,
    vendor_name TEXT,
    rank TEXT,
    make TEXT,
    model TEXT,
    basic_rate TEXT,
    gst_percent TEXT,
    unit_rate_incl_gst TEXT,
    bfc_date TEXT,
    rc_valid_upto TEXT,
    tender_quantity TEXT,
    remarks TEXT,
    department TEXT,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES source_files(file_id),
    FOREIGN KEY(sheet_id) REFERENCES source_sheets(sheet_id)
);

CREATE INDEX IF NOT EXISTS idx_rc_items_batch ON rc_items(batch_id);

CREATE TABLE IF NOT EXISTS tender_items (
    tender_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    sheet_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    tender_no TEXT,
    source_item_name TEXT,
    tender_description TEXT,
    qty TEXT,
    no_of_responses TEXT,
    bid_start_date TEXT,
    pre_bid_date TEXT,
    bid_close_date TEXT,
    tender_stage TEXT,
    case_worker TEXT,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES source_files(file_id),
    FOREIGN KEY(sheet_id) REFERENCES source_sheets(sheet_id)
);

CREATE INDEX IF NOT EXISTS idx_tender_items_batch ON tender_items(batch_id);

CREATE TABLE IF NOT EXISTS po_lines (
    po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    sheet_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    po_no TEXT,
    po_date TEXT,
    gross_amount TEXT,
    vendor_name TEXT,
    source_item_name TEXT,
    ordered_qty TEXT,
    unit_rate_incl_gst TEXT,
    total_amount TEXT,
    institution_type TEXT,
    location TEXT,
    district TEXT,
    scheme TEXT,
    hod TEXT,
    budget TEXT,
    delivery_period TEXT,
    case_worker_name TEXT,
    remarks TEXT,
    agt_no TEXT,
    agt_date TEXT,
    make TEXT,
    model TEXT,
    tender_no TEXT,
    tender_date TEXT,
    bfc_date TEXT,
    equip_fun TEXT,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES source_files(file_id),
    FOREIGN KEY(sheet_id) REFERENCES source_sheets(sheet_id)
);

CREATE INDEX IF NOT EXISTS idx_po_lines_batch ON po_lines(batch_id);

CREATE TABLE IF NOT EXISTS indent_lifecycle (
    lifecycle_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    indent_line_id INTEGER NOT NULL,
    indent_header_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    sheet_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    source_item_name TEXT,
    normalized_item_name TEXT,
    required_qty TEXT,
    rc_candidate_count INTEGER NOT NULL,
    tender_candidate_count INTEGER NOT NULL,
    po_candidate_count INTEGER NOT NULL,
    matched_rc_ids TEXT,
    matched_tender_ids TEXT,
    matched_po_ids TEXT,
    confirmed_ordered_qty TEXT,
    po_pending_qty TEXT,
    current_lifecycle_status TEXT,
    match_type TEXT,
    match_score REAL,
    confidence_score REAL,
    review_status TEXT,
    exception_count INTEGER NOT NULL,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(indent_header_id) REFERENCES indent_headers(indent_header_id),
    FOREIGN KEY(file_id) REFERENCES source_files(file_id),
    FOREIGN KEY(sheet_id) REFERENCES source_sheets(sheet_id)
);

CREATE INDEX IF NOT EXISTS idx_indent_lifecycle_batch ON indent_lifecycle(batch_id);

CREATE TABLE IF NOT EXISTS po_allocations (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    lifecycle_id INTEGER,
    indent_line_id INTEGER NOT NULL,
    indent_header_id INTEGER NOT NULL,
    po_line_id INTEGER NOT NULL,
    allocation_order INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    source_item_name TEXT,
    po_no TEXT,
    po_date TEXT,
    ordered_qty TEXT,
    allocated_qty TEXT,
    remaining_indent_qty TEXT,
    allocation_status TEXT,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(lifecycle_id) REFERENCES indent_lifecycle(lifecycle_id),
    FOREIGN KEY(indent_line_id) REFERENCES indent_lines(indent_line_id),
    FOREIGN KEY(indent_header_id) REFERENCES indent_headers(indent_header_id),
    FOREIGN KEY(po_line_id) REFERENCES po_lines(po_line_id)
);

CREATE INDEX IF NOT EXISTS idx_po_allocations_batch ON po_allocations(batch_id);

CREATE TABLE IF NOT EXISTS exceptions (
    exception_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    file_id INTEGER,
    sheet_id INTEGER,
    row_id INTEGER,
    exception_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exceptions_batch ON exceptions(batch_id);
"""


class ReconciliationDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def initialize(self) -> None:
        connection = self.connect()
        connection.executescript(SCHEMA_SQL)
        connection.commit()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Add columns introduced after a database file was first created.
        `CREATE TABLE IF NOT EXISTS` does not alter existing tables, so older
        on-disk databases need an explicit, idempotent ALTER TABLE."""
        connection = self.connect()
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(indent_lifecycle)")}
        if "confidence_score" not in existing_columns:
            connection.execute("ALTER TABLE indent_lifecycle ADD COLUMN confidence_score REAL")
        connection.commit()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def begin_batch(self, batch: BatchSummary) -> None:
        connection = self.connect()
        connection.execute(
            """
            INSERT OR REPLACE INTO run_batches (
                batch_id, root_path, started_at, status,
                files_discovered, files_ingested, duplicate_files,
                sheets_ingested, rows_ingested, exceptions_created,
                output_path, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch.batch_id,
                batch.root_path,
                datetime.utcnow().isoformat(timespec="seconds"),
                batch.status,
                batch.files_discovered,
                batch.files_ingested,
                batch.duplicate_files,
                batch.sheets_ingested,
                batch.rows_ingested,
                batch.exceptions_created,
                batch.output_path or None,
                None,
            ),
        )
        connection.commit()

    def complete_batch(self, batch: BatchSummary) -> None:
        connection = self.connect()
        connection.execute(
            """
            UPDATE run_batches
            SET completed_at = ?, status = ?, files_discovered = ?, files_ingested = ?, duplicate_files = ?,
                sheets_ingested = ?, rows_ingested = ?, exceptions_created = ?, output_path = ?
            WHERE batch_id = ?
            """,
            (
                datetime.utcnow().isoformat(timespec="seconds"),
                batch.status,
                batch.files_discovered,
                batch.files_ingested,
                batch.duplicate_files,
                batch.sheets_ingested,
                batch.rows_ingested,
                batch.exceptions_created,
                batch.output_path or None,
                batch.batch_id,
            ),
        )
        connection.commit()

    def file_hash_exists(self, file_hash: str) -> Optional[int]:
        row = self.connect().execute(
            """
            SELECT f.file_id FROM source_files f WHERE f.file_hash = ? AND (
                (f.source_type = 'Indent' AND EXISTS (SELECT 1 FROM indent_lines i WHERE i.file_id = f.file_id)) OR
                (f.source_type = 'RC' AND EXISTS (SELECT 1 FROM rc_items r WHERE r.file_id = f.file_id)) OR
                (f.source_type = 'Tender' AND EXISTS (SELECT 1 FROM tender_items t WHERE t.file_id = f.file_id)) OR
                (f.source_type = 'PO' AND EXISTS (SELECT 1 FROM po_lines p WHERE p.file_id = f.file_id))
            ) ORDER BY f.file_id DESC LIMIT 1
            """,
            (file_hash,),
        ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def record_file(self, record: FileRecord) -> int:
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO source_files (
                batch_id, source_type, folder_name, file_name, file_path,
                file_hash, file_size, modified_at, import_status,
                duplicate_of_file_id, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.batch_id,
                record.source_type,
                record.folder_name,
                record.file_name,
                str(record.file_path),
                record.file_hash,
                record.file_size,
                record.modified_at,
                record.status,
                record.duplicate_of_file_id,
                record.note,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def record_sheet(self, record: SheetRecord) -> int:
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO source_sheets (
                file_id, batch_id, source_type, sheet_name, header_row_index,
                row_count, column_count, detected_headers_json, import_status, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.file_id,
                record.batch_id,
                record.source_type,
                record.sheet_name,
                record.header_row_index,
                record.row_count,
                record.column_count,
                json_dumps(record.detected_headers),
                record.status,
                record.note,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def record_rows(self, records: Sequence[RowRecord]) -> int:
        if not records:
            return 0
        connection = self.connect()
        connection.executemany(
            """
            INSERT INTO source_rows (
                file_id, sheet_id, batch_id, source_type, sheet_name,
                row_number, header_row_index, row_kind, row_hash,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.file_id,
                    record.sheet_id,
                    record.batch_id,
                    record.source_type,
                    record.sheet_name,
                    record.row_number,
                    record.header_row_index,
                    record.row_kind,
                    record.row_hash,
                    json_dumps(record.payload),
                    datetime.utcnow().isoformat(timespec="seconds"),
                )
                for record in records
            ],
        )
        connection.commit()
        return len(records)

    def record_indent_header(self, record: IndentHeaderRecord) -> int:
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO indent_headers (
                batch_id, file_id, sheet_id, source_file, source_sheet, source_row,
                indent_no, indent_date, institution_text, institution_name, district,
                as_number, as_amount, budget_head, department, source_title, raw_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.batch_id,
                record.file_id,
                record.sheet_id,
                record.source_file,
                record.source_sheet,
                record.source_row,
                record.indent_no,
                record.indent_date,
                record.institution_text,
                record.institution_name,
                record.district,
                record.as_number,
                record.as_amount,
                record.budget_head,
                record.department,
                record.source_title,
                json_dumps(record.raw_payload),
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def record_indent_lines(self, records: Sequence[IndentLineRecord]) -> int:
        if not records:
            return 0
        connection = self.connect()
        connection.executemany(
            """
            INSERT INTO indent_lines (
                batch_id, file_id, sheet_id, indent_header_id, source_file, source_sheet,
                source_row, source_serial_no, department, source_item_name,
                normalized_item_name, required_qty, unit_of_measure, raw_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.batch_id,
                    record.file_id,
                    record.sheet_id,
                    record.indent_header_id,
                    record.source_file,
                    record.source_sheet,
                    record.source_row,
                    record.source_serial_no,
                    record.department,
                    record.source_item_name,
                    record.normalized_item_name,
                    record.required_qty,
                    record.unit_of_measure,
                    json_dumps(record.raw_payload),
                    datetime.utcnow().isoformat(timespec="seconds"),
                )
                for record in records
            ],
        )
        connection.commit()
        return len(records)

    def record_rc_items(self, records: Sequence[RCRecord]) -> int:
        if not records:
            return 0
        connection = self.connect()
        connection.executemany(
            """
            INSERT INTO rc_items (
                batch_id, file_id, sheet_id, source_file, source_sheet, source_row,
                rc_group_no, source_item_name, vendor_name, rank, make, model,
                basic_rate, gst_percent, unit_rate_incl_gst, bfc_date, rc_valid_upto,
                tender_quantity, remarks, department, raw_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.batch_id,
                    record.file_id,
                    record.sheet_id,
                    record.source_file,
                    record.source_sheet,
                    record.source_row,
                    record.rc_group_no,
                    record.source_item_name,
                    record.vendor_name,
                    record.rank,
                    record.make,
                    record.model,
                    record.basic_rate,
                    record.gst_percent,
                    record.unit_rate_incl_gst,
                    record.bfc_date,
                    record.rc_valid_upto,
                    record.tender_quantity,
                    record.remarks,
                    record.department,
                    json_dumps(record.raw_payload),
                    datetime.utcnow().isoformat(timespec="seconds"),
                )
                for record in records
            ],
        )
        connection.commit()
        return len(records)

    def record_tender_items(self, records: Sequence[TenderRecord]) -> int:
        if not records:
            return 0
        connection = self.connect()
        connection.executemany(
            """
            INSERT INTO tender_items (
                batch_id, file_id, sheet_id, source_file, source_sheet, source_row,
                tender_no, source_item_name, tender_description, qty, no_of_responses,
                bid_start_date, pre_bid_date, bid_close_date, tender_stage, case_worker,
                raw_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.batch_id,
                    record.file_id,
                    record.sheet_id,
                    record.source_file,
                    record.source_sheet,
                    record.source_row,
                    record.tender_no,
                    record.source_item_name,
                    record.tender_description,
                    record.qty,
                    record.no_of_responses,
                    record.bid_start_date,
                    record.pre_bid_date,
                    record.bid_close_date,
                    record.tender_stage,
                    record.case_worker,
                    json_dumps(record.raw_payload),
                    datetime.utcnow().isoformat(timespec="seconds"),
                )
                for record in records
            ],
        )
        connection.commit()
        return len(records)

    def record_po_lines(self, records: Sequence[PORowRecord]) -> int:
        if not records:
            return 0
        connection = self.connect()
        connection.executemany(
            """
            INSERT INTO po_lines (
                batch_id, file_id, sheet_id, source_file, source_sheet, source_row,
                po_no, po_date, gross_amount, vendor_name, source_item_name, ordered_qty,
                unit_rate_incl_gst, total_amount, institution_type, location, district,
                scheme, hod, budget, delivery_period, case_worker_name, remarks, agt_no,
                agt_date, make, model, tender_no, tender_date, bfc_date, equip_fun,
                raw_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.batch_id,
                    record.file_id,
                    record.sheet_id,
                    record.source_file,
                    record.source_sheet,
                    record.source_row,
                    record.po_no,
                    record.po_date,
                    record.gross_amount,
                    record.vendor_name,
                    record.source_item_name,
                    record.ordered_qty,
                    record.unit_rate_incl_gst,
                    record.total_amount,
                    record.institution_type,
                    record.location,
                    record.district,
                    record.scheme,
                    record.hod,
                    record.budget,
                    record.delivery_period,
                    record.case_worker_name,
                    record.remarks,
                    record.agt_no,
                    record.agt_date,
                    record.make,
                    record.model,
                    record.tender_no,
                    record.tender_date,
                    record.bfc_date,
                    record.equip_fun,
                    json_dumps(record.raw_payload),
                    datetime.utcnow().isoformat(timespec="seconds"),
                )
                for record in records
            ],
        )
        connection.commit()
        return len(records)

    def record_lifecycle_rows(self, records: Sequence[LifecycleRecord], *, commit: bool = True) -> int:
        if not records:
            return 0
        connection = self.connect()
        connection.executemany(
            """
            INSERT INTO indent_lifecycle (
                batch_id, indent_line_id, indent_header_id, file_id, sheet_id, source_file, source_sheet,
                source_row, source_item_name, normalized_item_name, required_qty, rc_candidate_count,
                tender_candidate_count, po_candidate_count, matched_rc_ids, matched_tender_ids,
                matched_po_ids, confirmed_ordered_qty, po_pending_qty, current_lifecycle_status,
                match_type, match_score, confidence_score, review_status, exception_count, raw_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.batch_id,
                    record.indent_line_id,
                    record.indent_header_id,
                    record.file_id,
                    record.sheet_id,
                    record.source_file,
                    record.source_sheet,
                    record.source_row,
                    record.source_item_name,
                    record.normalized_item_name,
                    record.required_qty,
                    record.rc_candidate_count,
                    record.tender_candidate_count,
                    record.po_candidate_count,
                    record.matched_rc_ids,
                    record.matched_tender_ids,
                    record.matched_po_ids,
                    record.confirmed_ordered_qty,
                    record.po_pending_qty,
                    record.current_lifecycle_status,
                    record.match_type,
                    record.match_score,
                    record.confidence_score,
                    record.review_status,
                    record.exception_count,
                    json_dumps(record.raw_payload),
                    datetime.utcnow().isoformat(timespec="seconds"),
                )
                for record in records
            ],
        )
        if commit:
            connection.commit()
        return len(records)

    def record_po_allocations(self, records: Sequence[POAllocationRecord], *, commit: bool = True) -> int:
        if not records:
            return 0
        connection = self.connect()
        connection.executemany(
            """
            INSERT INTO po_allocations (
                batch_id, lifecycle_id, indent_line_id, indent_header_id, po_line_id, allocation_order,
                source_file, source_sheet, source_row, source_item_name, po_no, po_date,
                ordered_qty, allocated_qty, remaining_indent_qty, allocation_status, raw_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.batch_id,
                    record.lifecycle_id,
                    record.indent_line_id,
                    record.indent_header_id,
                    record.po_line_id,
                    record.allocation_order,
                    record.source_file,
                    record.source_sheet,
                    record.source_row,
                    record.source_item_name,
                    record.po_no,
                    record.po_date,
                    record.ordered_qty,
                    record.allocated_qty,
                    record.remaining_indent_qty,
                    record.allocation_status,
                    json_dumps(record.raw_payload),
                    datetime.utcnow().isoformat(timespec="seconds"),
                )
                for record in records
            ],
        )
        if commit:
            connection.commit()
        return len(records)

    def replace_reconciliation(self, lifecycle: Sequence[LifecycleRecord], allocations: Sequence[POAllocationRecord]) -> None:
        """Atomically replace derived results only; source data and lineage stay intact."""
        connection = self.connect()
        with connection:
            connection.execute("DELETE FROM po_allocations")
            connection.execute("DELETE FROM indent_lifecycle")
            self.record_lifecycle_rows(lifecycle, commit=False)
            ids = dict(connection.execute("SELECT indent_line_id, lifecycle_id FROM indent_lifecycle"))
            for allocation in allocations:
                allocation.lifecycle_id = ids[allocation.indent_line_id]
            self.record_po_allocations(allocations, commit=False)

    def record_exception(
        self,
        batch_id: str,
        exception_code: str,
        severity: str,
        status: str,
        summary: str,
        details: Optional[Dict[str, Any]] = None,
        file_id: Optional[int] = None,
        sheet_id: Optional[int] = None,
        row_id: Optional[int] = None,
    ) -> int:
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO exceptions (
                batch_id, file_id, sheet_id, row_id, exception_code,
                severity, status, summary, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                file_id,
                sheet_id,
                row_id,
                exception_code,
                severity,
                status,
                summary,
                json_dumps(details or {}),
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def fetch_dataframe(self, query: str, params: Sequence[Any] = ()) -> pd.DataFrame:
        connection = self.connect()
        return pd.read_sql_query(query, connection, params=params)
