from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class FileRecord:
    batch_id: str
    source_type: str
    folder_name: str
    file_name: str
    file_path: Path
    file_hash: str
    file_size: int
    modified_at: str
    status: str = "new"
    note: str = ""
    duplicate_of_file_id: Optional[int] = None


@dataclass(slots=True)
class SheetRecord:
    batch_id: str
    file_id: Optional[int]
    source_type: str
    sheet_name: str
    header_row_index: int
    row_count: int
    column_count: int
    detected_headers: List[str] = field(default_factory=list)
    status: str = "new"
    note: str = ""


@dataclass(slots=True)
class RowRecord:
    batch_id: str
    file_id: Optional[int]
    sheet_id: Optional[int]
    source_type: str
    sheet_name: str
    row_number: int
    header_row_index: int
    row_kind: str
    row_hash: str
    payload: Dict[str, Any]


@dataclass(slots=True)
class IndentHeaderRecord:
    batch_id: str
    file_id: int
    sheet_id: int
    source_file: str
    source_sheet: str
    source_row: int
    indent_no: str
    indent_date: str
    institution_text: str
    institution_name: str
    district: str
    as_number: str
    as_amount: str
    budget_head: str
    department: str
    source_title: str
    raw_payload: Dict[str, Any]


@dataclass(slots=True)
class IndentLineRecord:
    batch_id: str
    file_id: int
    sheet_id: int
    indent_header_id: Optional[int]
    source_file: str
    source_sheet: str
    source_row: int
    source_serial_no: str
    department: str
    source_item_name: str
    normalized_item_name: str
    required_qty: str
    unit_of_measure: str
    raw_payload: Dict[str, Any]


@dataclass(slots=True)
class RCRecord:
    batch_id: str
    file_id: int
    sheet_id: int
    source_file: str
    source_sheet: str
    source_row: int
    rc_group_no: str
    source_item_name: str
    vendor_name: str
    rank: str
    make: str
    model: str
    basic_rate: str
    gst_percent: str
    unit_rate_incl_gst: str
    bfc_date: str
    rc_valid_upto: str
    tender_quantity: str
    remarks: str
    department: str
    raw_payload: Dict[str, Any]


@dataclass(slots=True)
class TenderRecord:
    batch_id: str
    file_id: int
    sheet_id: int
    source_file: str
    source_sheet: str
    source_row: int
    tender_no: str
    source_item_name: str
    tender_description: str
    qty: str
    no_of_responses: str
    bid_start_date: str
    pre_bid_date: str
    bid_close_date: str
    tender_stage: str
    case_worker: str
    raw_payload: Dict[str, Any]


@dataclass(slots=True)
class PORowRecord:
    batch_id: str
    file_id: int
    sheet_id: int
    source_file: str
    source_sheet: str
    source_row: int
    po_no: str
    po_date: str
    gross_amount: str
    vendor_name: str
    source_item_name: str
    ordered_qty: str
    unit_rate_incl_gst: str
    total_amount: str
    institution_type: str
    location: str
    district: str
    scheme: str
    hod: str
    budget: str
    delivery_period: str
    case_worker_name: str
    remarks: str
    agt_no: str
    agt_date: str
    make: str
    model: str
    tender_no: str
    tender_date: str
    bfc_date: str
    equip_fun: str
    raw_payload: Dict[str, Any]


@dataclass(slots=True)
class LifecycleRecord:
    batch_id: str
    indent_line_id: int
    indent_header_id: int
    file_id: int
    sheet_id: int
    source_file: str
    source_sheet: str
    source_row: int
    source_item_name: str
    normalized_item_name: str
    required_qty: str
    rc_candidate_count: int
    tender_candidate_count: int
    po_candidate_count: int
    matched_rc_ids: str
    matched_tender_ids: str
    matched_po_ids: str
    confirmed_ordered_qty: str
    po_pending_qty: str
    current_lifecycle_status: str
    match_type: str
    match_score: float
    review_status: str
    exception_count: int
    raw_payload: Dict[str, Any]
    confidence_score: float = 0.0


@dataclass(slots=True)
class POAllocationRecord:
    batch_id: str
    lifecycle_id: Optional[int]
    indent_line_id: int
    indent_header_id: int
    po_line_id: int
    allocation_order: int
    source_file: str
    source_sheet: str
    source_row: int
    source_item_name: str
    po_no: str
    po_date: str
    ordered_qty: str
    allocated_qty: str
    remaining_indent_qty: str
    allocation_status: str
    raw_payload: Dict[str, Any]


@dataclass(slots=True)
class BatchSummary:
    batch_id: str
    root_path: str
    files_discovered: int = 0
    files_ingested: int = 0
    duplicate_files: int = 0
    sheets_ingested: int = 0
    rows_ingested: int = 0
    exceptions_created: int = 0
    output_path: str = ""
    status: str = "started"


@dataclass(slots=True)
class HeaderDetectionResult:
    row_index: Optional[int]
    confidence: float
    headers: List[str]
    notes: str = ""


@dataclass(slots=True)
class SheetSnapshot:
    sheet_name: str
    rows: List[List[Any]]
    header_detection: HeaderDetectionResult


@dataclass(slots=True)
class WorkbookSnapshot:
    file_path: Path
    sheets: List[SheetSnapshot]
