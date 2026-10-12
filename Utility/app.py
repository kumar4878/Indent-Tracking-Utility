from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config_loader import load_app_config, load_json
from database_service import ReconciliationDatabase
from mapping_engine import suggest_column_mapping
from pipeline import run_inventory_scan
from report_generator import build_report


st.set_page_config(page_title="TGMSIDC Indent Tracker", layout="wide")

config_path = ROOT / "config" / "AppConfig.json"
config = load_app_config(config_path)
mapping_rules = load_json(Path(str(config["mapping_file"])))

database = ReconciliationDatabase(Path(str(config["database_path"])))
database.initialize()

st.title("TGMSIDC Indent-to-Procurement Reconciliation Utility")
st.caption("Inventory, lineage, and initial reporting foundation for the indent lifecycle." )

left, middle, right = st.columns(3)
left.metric("Input Root", config["root_path"])
middle.metric("Output Folder", config["output_folder"])
right.metric("Supported Types", ", ".join(str(item) for item in config.get("supported_extensions", [])))

if st.button("Run inventory scan", type="primary"):
    with st.spinner("Scanning input folders and storing lineage..."):
        batch = run_inventory_scan(config, database)
        st.session_state["last_batch_id"] = batch.batch_id
        st.session_state["last_report"] = ""
        st.success(f"Scan completed for batch {batch.batch_id}")
        st.write({
            "files_discovered": batch.files_discovered,
            "files_ingested": batch.files_ingested,
            "duplicate_files": batch.duplicate_files,
            "sheets_ingested": batch.sheets_ingested,
            "rows_ingested": batch.rows_ingested,
            "exceptions_created": batch.exceptions_created,
            "status": batch.status,
        })

if st.button("Build Excel report"):
    with st.spinner("Generating workbook..."):
        with warnings.catch_warnings(record=True) as report_warnings:
            warnings.simplefilter("always", RuntimeWarning)
            report_path = build_report(database, config)
        st.session_state["last_report"] = str(report_path)
        st.success(f"Report written to {report_path}")
        for warning in report_warnings:
            st.warning(str(warning.message))

summary_frame = database.fetch_dataframe("SELECT * FROM run_batches ORDER BY started_at DESC LIMIT 5")
indent_header_frame = database.fetch_dataframe("SELECT * FROM indent_headers ORDER BY indent_header_id DESC LIMIT 25")
indent_line_frame = database.fetch_dataframe("SELECT * FROM indent_lines ORDER BY indent_line_id DESC LIMIT 50")
life_frame = database.fetch_dataframe("SELECT * FROM indent_lifecycle ORDER BY lifecycle_id DESC LIMIT 50")
allocation_frame = database.fetch_dataframe("SELECT * FROM po_allocations ORDER BY allocation_id DESC LIMIT 50")
rc_frame = database.fetch_dataframe("SELECT * FROM rc_items ORDER BY rc_item_id DESC LIMIT 25")
tender_frame = database.fetch_dataframe("SELECT * FROM tender_items ORDER BY tender_item_id DESC LIMIT 25")
po_frame = database.fetch_dataframe("SELECT * FROM po_lines ORDER BY po_line_id DESC LIMIT 25")
file_frame = database.fetch_dataframe("SELECT * FROM source_files ORDER BY file_id DESC LIMIT 25")
sheet_frame = database.fetch_dataframe("SELECT * FROM source_sheets ORDER BY sheet_id DESC LIMIT 25")
exception_frame = database.fetch_dataframe("SELECT * FROM exceptions ORDER BY exception_id DESC LIMIT 25")

summary_tab, indent_data_tab, lifecycle_tab, allocation_tab, rc_data_tab, tender_data_tab, po_data_tab, files_tab, sheets_tab, exceptions_tab, mapping_tab = st.tabs([
    "Run Summary",
    "Indent Data",
    "Lifecycle",
    "PO Allocations",
    "RC Data",
    "Tender Data",
    "PO Data",
    "Files",
    "Sheets",
    "Exceptions",
    "Header Mapping",
])

with summary_tab:
    st.dataframe(summary_frame, use_container_width=True, hide_index=True)
    if st.session_state.get("last_report"):
        st.info(f"Latest report: {st.session_state['last_report']}")

with indent_data_tab:
    st.subheader("Indent Header")
    st.dataframe(indent_header_frame, use_container_width=True, hide_index=True)
    st.subheader("Indent Lines")
    st.dataframe(indent_line_frame, use_container_width=True, hide_index=True)

with lifecycle_tab:
    st.dataframe(life_frame, use_container_width=True, hide_index=True)

with allocation_tab:
    st.dataframe(allocation_frame, use_container_width=True, hide_index=True)

with rc_data_tab:
    st.dataframe(rc_frame, use_container_width=True, hide_index=True)

with tender_data_tab:
    st.dataframe(tender_frame, use_container_width=True, hide_index=True)

with po_data_tab:
    st.dataframe(po_frame, use_container_width=True, hide_index=True)

with files_tab:
    st.dataframe(file_frame, use_container_width=True, hide_index=True)

with sheets_tab:
    st.dataframe(sheet_frame, use_container_width=True, hide_index=True)

with exceptions_tab:
    st.dataframe(exception_frame, use_container_width=True, hide_index=True)

with mapping_tab:
    if not sheet_frame.empty:
        selected_sheet_id = st.selectbox("Select a sheet to inspect", sheet_frame["sheet_id"].tolist())
        selected_sheet = sheet_frame[sheet_frame["sheet_id"] == selected_sheet_id].iloc[0]
        row = database.connect().execute(
            "SELECT detected_headers_json, source_type FROM source_sheets WHERE sheet_id = ?",
            (int(selected_sheet_id),),
        ).fetchone()
        headers = []
        if row is not None and row[0]:
            import json

            headers = json.loads(row[0])
        if headers:
            suggestions = pd.DataFrame(suggest_column_mapping(headers, row[1], mapping_rules))
            st.dataframe(suggestions, use_container_width=True, hide_index=True)
        else:
            st.warning("No headers were detected for the selected sheet.")
    else:
        st.info("Run an inventory scan to inspect mappings.")
