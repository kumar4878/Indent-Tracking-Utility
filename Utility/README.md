# TGMSIDC Indent Tracking Utility

This is the initial pilot foundation for the indent-to-procurement reconciliation utility described in the PRD.

## What it does now
- scans the configured input folders
- fingerprints workbook files with SHA-256
- detects workbook sheets and likely header rows
- stores file, sheet, row, and lineage data in SQLite
- generates a report-ready Excel workbook
- exposes a Streamlit UI for inventory and reporting

## Setup
1. Create a Python environment.
2. Install dependencies:
   ```bash
   pip install -r Utility/requirements.txt
   ```
3. Run the app:
   ```bash
   streamlit run Utility/app.py
   ```

## Config
The main settings live in `Utility/config/AppConfig.json`.

## PO reconciliation and tracker output
- Hospital matching ignores punctuation/case and standardizes known institution abbreviations (for example, `AH, Choppadandi` and `Area Hospital Choppadandi`). A trailing `Dept. of ...` is treated as a hospital department. Both facility and district must be known and agree; other hospitals are never accepted through fuzzy fallback.
- PO item links require an exact normalized/approved-alias match or a whole-name similarity at the configured `item_name_threshold`. Numeric specification differences block confirmation. Weaker candidates remain for review and do not populate confirmed PO numbers or ordered quantities.
- PO quantities are shared across indent lines, never reused beyond the source quantity. Exact matches are allocated before fuzzy matches, then in indent-line order. Department-specific allocation still requires review where the indent has no corresponding department evidence.
- Each PO cell has an Excel note with its source evidence or review candidates, without changing the tracker template's columns or layout. Add only reviewed equipment aliases to `approved_aliases` in `MatchingRules.json` and rerun the scan to resolve naming differences.
- A scan rebuilds the derived lifecycle/allocation snapshot instead of appending stale matches. Inventory-only legacy imports with no extracted records are eligible for reimport; original lineage is retained.
- If the Latest workbook is open in Excel, the timestamped report is still saved and a warning identifies the unchanged Latest copy. Open the new timestamped report or close Excel and regenerate.

## Regression tests
Run `python -m unittest discover -s Utility/tests -v` from the workspace root. Tests include the supplied source workbooks when present, valid Choppadandi matches, rejection of Nakrekal PO 345A, quantity caps, rerun idempotency, rollback, and output file locking.
