# TGMSIDC Indent-to-Procurement Reconciliation Utility

## Updated Product Requirements Document, Matching Catalogue and VS Code Implementation Plan

**Version:** 1.2  
**Document Status:** Updated baseline for development  
**Prepared Date:** 08 October 2026  
**Development Environment:** Visual Studio Code  
**Proposed Stack:** Python, pandas, openpyxl, RapidFuzz, Streamlit, SQLite for pilot  
**Configured Input Root:** `C:\VSCode Projects\Indent Tracker\Files`  
**Primary Output Folder:** `C:\VSCode Projects\Indent Tracker\Files\Output File`

---

# 1. Product Objective

Build an internal reconciliation utility that reads heterogeneous Excel workbooks maintained by different TGMSIDC resources, standardizes their structures, and produces facility-wise and item-wise end-to-end visibility across:

```text
Indent → RC Availability → Tender → BFC / RC Creation → PO → Ordered Quantity → Pending Quantity
```

The utility must answer, for every facility and every indent item:

1. What was originally requested?
2. What quantity was requested?
3. Is the item still Required or Not Required?
4. Is an active Rate Contract available?
5. If no valid RC exists, is a Tender required?
6. Has a Tender been initiated?
7. What is the Tender Item stage and BFC outcome?
8. Has one or more PO been issued?
9. How much quantity has been ordered?
10. How much remains pending for PO?
11. Was the PO item an exact match, standardized alias, approved substitute or technical upgradation?
12. Is manual review required?
13. Can every result be traced to the original file, sheet and row?

The utility is initially a reconciliation and management-reporting solution. It is not the final transaction-entry, approval, vendor, delivery, QA or payment application.

---

# 2. Confirmed Folder Structure

```text
C:\VSCode Projects\Indent Tracker\Files\
│
├── Indents\
│   └── One or more Indent Excel workbooks
│
├── Rate Contracts\
│   └── One or more RC Excel workbooks
│
├── Tenders\
│   └── One or more Tender Excel workbooks
│
├── Purchase Orders\
│   └── One or more PO Excel workbooks
│
└── Output File\
    └── Derived data, reconciliation outputs and report-ready workbooks
```

## 2.1 Folder-to-Source Mapping

| Folder | Internal Source Type | Initial Expected Files |
|---|---|---:|
| `Indents` | `Indent` | 2 |
| `Rate Contracts` | `RC` | 1 |
| `Tenders` | `Tender` | 1 |
| `Purchase Orders` | `PO` | 2 |
| `Output File` | `Output` | Generated |

The parent folder determines source type. The utility must not depend on file naming conventions to determine whether a workbook is an Indent, RC, Tender or PO source.

---

# 3. Application Configuration

Create `Utility\config\AppConfig.json`:

```json
{
  "root_path": "C:\\VSCode Projects\\Indent Tracker\\Files",
  "input_folders": {
    "Indent": "Indents",
    "RC": "Rate Contracts",
    "Tender": "Tenders",
    "PO": "Purchase Orders"
  },
  "output_folder": "Output File",
  "supported_extensions": [".xlsx", ".xlsm", ".xls"],
  "recursive_scan": false,
  "preserve_source_files": true,
  "overwrite_source": false,
  "create_timestamped_output": true,
  "create_latest_output": true,
  "database_path": "C:\\VSCode Projects\\Indent Tracker\\Utility\\database\\tgmsidc_reconciliation.db",
  "mapping_file": "C:\\VSCode Projects\\Indent Tracker\\Utility\\config\\SrcDestMapping.json",
  "matching_rules_file": "C:\\VSCode Projects\\Indent Tracker\\Utility\\config\\MatchingRules.json",
  "status_rules_file": "C:\\VSCode Projects\\Indent Tracker\\Utility\\config\\StatusRules.json"
}
```

## 3.1 File Handling Rules

- The utility shall treat input folders as read-only.
- The utility shall never modify, rename, move or delete an input file.
- Each imported file shall receive a SHA-256 fingerprint.
- Identical content shall not be silently imported twice.
- A changed file with the same name shall be treated as a new version.
- Every execution shall receive an `ImportBatchID`.
- The latest successful output may replace `TGMSIDC_Indent_Lifecycle_Latest.xlsx`.
- A failed or incomplete run shall not replace the latest successful output.

---

# 4. Recommended Visual Studio Code Project Structure

```text
C:\VSCode Projects\Indent Tracker\
│
├── Utility\
│   ├── app.py
│   ├── requirements.txt
│   ├── README.md
│   ├── config\
│   │   ├── AppConfig.json
│   │   ├── SrcDestMapping.json
│   │   ├── MatchingRules.json
│   │   └── StatusRules.json
│   ├── src\
│   │   ├── folder_scanner.py
│   │   ├── excel_reader.py
│   │   ├── header_detector.py
│   │   ├── mapping_engine.py
│   │   ├── cleaning_engine.py
│   │   ├── institution_matcher.py
│   │   ├── equipment_matcher.py
│   │   ├── vendor_matcher.py
│   │   ├── rc_matcher.py
│   │   ├── tender_matcher.py
│   │   ├── po_matcher.py
│   │   ├── allocation_engine.py
│   │   ├── reconciliation_engine.py
│   │   ├── status_engine.py
│   │   ├── exception_engine.py
│   │   ├── database_service.py
│   │   └── report_generator.py
│   ├── pages\
│   │   ├── 01_Folder_Scan.py
│   │   ├── 02_Column_Mapping.py
│   │   ├── 03_Institution_Mapping.py
│   │   ├── 04_Equipment_Mapping.py
│   │   ├── 05_RC_Tender_Review.py
│   │   ├── 06_PO_Match_Review.py
│   │   ├── 07_Substitutions.py
│   │   ├── 08_Exceptions.py
│   │   └── 09_Reports.py
│   ├── database\
│   │   └── tgmsidc_reconciliation.db
│   ├── tests\
│   └── logs\
│
└── Files\
    ├── Indents\
    ├── Rate Contracts\
    ├── Tenders\
    ├── Purchase Orders\
    └── Output File\
```

---

# 5. Source-to-Destination Column Mapping

The utility shall use `SrcDestMapping.json`. Mapping shall be maintained separately for Indent, RC, Tender and PO sources.

## 5.1 Header Normalization

Before matching a source column, the utility shall:

- remove line breaks and HTML tags;
- trim spaces;
- collapse repeated spaces;
- compare case-insensitively;
- normalize punctuation for matching;
- preserve the original heading for audit.

Examples:

```text
PO.\nNO.                       → PO. NO.
Hospital/\nInstitution\nType     → Hospital/ Institution Type
Unit Rate incl.of GST\n        → Unit Rate incl.of GST
```

## 5.2 Initial Alias Examples

```text
Sno / Sl.No / S.No                         → SourceSerialNo
Indent Number / Indent No / Indent / IndNo → IndentNo
District / Dist. / Dist                     → District
Hospital / Hospital Name / Hosptial         → Hospital
Equipment Name / Item Name / ITEMNAME       → SourceItemName
Required Qty / Qty / Quantity               → RequiredQty
PO. NO. / PO No / PONo                      → PONo
Item Qty / Ordered Qty                      → OrderedQty
FIRM NAME / Firm Name / Vendor              → VendorName
```

`SourceSerialNo` and `IndentNo` are different fields. A serial number must not be treated as an Indent Number unless explicitly confirmed.

## 5.3 Mapping Review Actions

The user shall be able to:

```text
Accept Suggested Mapping
Select Different Destination
Ignore Optional Column
Create New Alias
Change Header Row
Reject Sheet
Save Mapping for Future Imports
```

An unmapped mandatory destination field shall block import for that sheet.

---

# 6. Canonical Data Model

## 6.1 Indent Header

```text
IndentID
IndentNo
IndentDate
InwardNo
InwardDate
HOD
InstitutionID
Hospital
District
ASNumber
ASDate
ASAmount
BudgetHead
CaseWorker
IndentHeaderStatus
SourceFile
SourceSheet
SourceRow
ImportBatchID
```

## 6.2 Indent Line

```text
IndentLineID
IndentID
SourceSerialNo
Department
SourceItemName
NormalizedItemName
EquipmentID
StandardItemName
ProcurementCategory
EquipmentType
RequiredQty
UnitOfMeasure
Prioritization
ValidationStatus
SourceFile
SourceSheet
SourceRow
```

## 6.3 Rate Contract

```text
RCID
RCNumber
RCItemID
TenderNo
SourceItemName
EquipmentID
StandardItemName
VendorID
VendorName
VendorRank
ApprovedRate
GSTPercentage
RCValidFrom
RCValidUpto
RCStatus
Make
Model
Warranty
SourceFile
SourceSheet
SourceRow
```

## 6.4 Tender

```text
TenderID
TenderNo
TenderItemID
TenderDate
SourceItemName
EquipmentID
StandardItemName
TenderStage
BFCStatus
BFCDate
TenderOutcome
CaseWorker
SourceFile
SourceSheet
SourceRow
```

## 6.5 Purchase Order

```text
POID
PONo
PODate
FileNo
GrossPOAmount
POLineID
POAllocationID
VendorID
VendorName
SourceItemName
EquipmentID
StandardItemName
OrderedQty
UnitOfMeasure
UnitRate
LineAmount
InstitutionID
Hospital
District
Location
SourceFinancialYear
SourceFile
SourceSheet
SourceRow
```

---

# 7. Institution and Facility Matching Catalogue

Institution matching shall use `InstitutionMaster` and `InstitutionAlias`.

## 7.1 Normalization

- normalize whitespace and punctuation;
- expand or standardize AH, Area Hospital, GMC, GGH, DH and CHC;
- extract district where embedded in the institution field;
- retain hospital type and district as separate attributes;
- preserve original text.

## 7.2 Match Levels

### H1. Exact Institution ID

Automatic confirmed match.

### H2. Approved Alias

Example:

```text
A.H. Choppadandi
Area Hospital Choppadandi
AH Choppadandi, Karimnagar
```

All may map to one approved Institution ID.

### H3. Exact Normalized Name + Exact District

Automatic match only when one candidate exists.

### H4. Strong Name Similarity + Exact District

```text
Name score ≥ 90
District exact/alias match
```

Strong candidate. Initial confirmation required; thereafter the saved alias may auto-map.

### H5. Name Similarity + Compatible Hospital Type

```text
Name score 85–89
Hospital type compatible
District compatible or missing
```

Manual review required.

### H6. District Conflict

Never auto-match.

### H7. Same Name in Multiple Districts

Never auto-match without district or Institution ID.

### H8. Parent Facility vs Department/Location

Example:

```text
GMC/GGH Wanaparthy - Principal Office
GMC/GGH Wanaparthy - Admin Office
```

Map to the same Institution ID while preserving the department/location separately.

## 7.3 Institution Match Outcomes

```text
Confirmed by ID
Confirmed by Alias
Confirmed by Name and District
Probable Institution Match
Multiple Institution Matches
District Conflict
Institution Not Found
Location Parsed from Institution Text
```

---

# 8. Equipment and Item Matching Catalogue

Item matching shall use `EquipmentMaster`, `EquipmentAlias`, technical attributes, package mappings and substitution mappings.

## 8.1 Item Normalization

The utility shall:

- remove HTML and line breaks;
- normalize punctuation and whitespace;
- standardize approved spelling aliases;
- standardize terminology only when meaning is unchanged;
- extract technical attributes;
- preserve original text.

Examples of spelling aliases:

```text
Syrange Pump    → Syringe Pump
Feotal Doppler  → Foetal Doppler
Radaint Warmer  → Radiant Warmer
Defibrilator    → Defibrillator
PhotoTheraphy   → Phototherapy Unit
```

## 8.2 Critical Technical Attributes

The utility must preserve and compare:

```text
Capacity: 100 mA, 200 mA, 5 litre/min, 10 litre/min
Parameters: 3 Para, 5 Para, 7 Para
Channels: 3 Channel, 12 Channel
Mobility: Mobile, Portable, Fixed
Patient Type: Adult, Paediatric, Neonatal
Scale: Major, Minor
Operation: Manual, Electronic, Hydraulic
Installation: Ceiling, Standing, Tabletop
Configuration: Single Bin, 2 Bin
Material: Stainless Steel, Wooden, Mixed
Unit: Number, Set, Pair, Metre
```

A high fuzzy score must not override a critical-attribute conflict.

## 8.3 Item Match Types

### I1. Exact Equipment ID

Automatic confirmed match.

### I2. Approved Alias Match

Same approved equipment master after spelling or naming normalization.

### I3. Exact Normalized Name Match

Confirmed only when critical attributes do not conflict.

### I4. Technical Attribute Match

Example:

```text
100 M.A. X-ray machine Mobile HF
100mA X-Ray Mobile
```

Core item, capacity and mobility agree.

### I5. Generic-to-Specific Match

Example:

```text
Office Table
Office Table Big Size
```

Manual review unless an approved substitution record exists.

### I6. Approved Technical Upgradation

Example:

```text
Indent: Monitors (5 Para), Qty 9
PO: Multipara Monitor (7 Para), Qty 9
PO: 214A
```

Match through `SubstitutionMapping`; preserve both equipment identities.

### I7. Approved Alternative Item

A technically different item approved to serve the same requirement. Approval reference is mandatory or must be marked `Reference Pending`.

### I8. Package / Component Match

Example:

```text
Indent: CR Machine, Qty 1
PO:
- Computed Radiography Machine, Qty 1
- 35 × 43 cm plate, Qty 1
- 24 × 30 cm plate, Qty 1
```

The CR system fulfills quantity 1. Component lines attach to the same package but do not increase fulfilled quantity to 3.

### I9. Bundled Indent Line

Example:

```text
Mechanised Laundry System containing multiple machines
```

Treat as a parent requirement with components. Manual decomposition may be required before reliable RC/PO matching.

### I10. Combined Requirement

Two or more indent lines may be combined into one standardized procurement item only after approval.

### I11. Split Procurement

One indent line may be fulfilled through multiple PO lines or vendors.

### I12. Partial Fulfilment

PO quantity is lower than required quantity.

### I13. Excess Quantity

Confirmed linked PO quantity exceeds the required quantity. Flag for review.

### I14. Accessory vs Main Equipment

Accessories shall not automatically fulfill the main-equipment quantity.

### I15. Probable Match

Text and attributes indicate similarity but confirmation is required.

### I16. Multiple Candidates

More than one indent item could match the PO line. No auto-link.

### I17. No Match

No defensible candidate exists.

## 8.4 Item Match Thresholds

```text
95–100: confirmed candidate only if unique and conflict-free
85–94: strong candidate, user confirmation required
70–84: probable candidate, mandatory review
Below 70: no automatic link
```

---

# 9. Quantity and Unit-of-Measure Use Cases

## Q1. Numeric Quantity

Store as numeric.

## Q2. Quantity with Unit

```text
1 Set → RequiredQty 1, UnitOfMeasure Set
40 Pairs → RequiredQty 40, UnitOfMeasure Pair
100 Metres → RequiredQty 100, UnitOfMeasure Metre
```

## Q3. Missing Quantity

Create `Quantity Missing` exception. Do not assume one.

## Q4. One Indent to Multiple POs

Aggregate only confirmed linked quantities.

## Q5. One PO to Multiple Indents

Require an explicit linked-quantity allocation for each Indent line.

## Q6. Package Components

Do not sum package components into the main required quantity.

## Q7. PO Pending Quantity

```text
POPendQty = MAX(RequiredQty - ConfirmedOrderedQty, 0)
```

## Q8. Supply Pending Quantity

When supply data is available:

```text
SupplyPendingQty = MAX(ConfirmedOrderedQty - SuppliedQty, 0)
```

Keep PO Pending and Supply Pending as separate fields.

---

# 10. RC Use Cases

```text
Active RC
RC Expiring Within 30 Days
RC Expiring Within 90 Days
RC Expiring Within 180 Days
Expired RC
RC Validity Missing
No RC
Multiple Active RCs
RC Equipment Attribute Conflict
RC Vendor Available but Item Not Applicable
RC Exists but PO Date Falls Outside Validity
```

Decision flow:

```text
Required + Active RC       → PO Route
Required + No/Expired RC   → Tender Route
Validity Missing           → RC Verification Hold
Not Required               → No Procurement Route
```

---

# 11. Tender Use Cases

Tender matching shall be at Tender Item level.

```text
Tender Not Initiated
Specification Confirmation
Tender Drafting
Tender Published
Pre-Bid Stage
Bid Submission Open
Bid Closed
Bid Opening
Technical Evaluation
Demonstration Stage
Financial Evaluation
Pending BFC
BFC Approved
Partially BFC Approved
BFC Deferred
Recalled
Retendered
Cancelled
Closed
```

Special cases:

- one Tender contains multiple items with different outcomes;
- BFC approved for some items and recalled for others;
- Tender is recalled and linked to a replacement Tender;
- PO exists but Tender stage is earlier than finalization;
- Tender item exists but no new RC is created;
- no active RC and no Tender item is found.

---

# 12. PO Matching and Reconciliation Use Cases

## P1. Exact Facility + Exact Item

Strongest normal match.

## P2. Facility Alias + Item Alias

Confirmed after master mapping.

## P3. Approved Substitute

Link using substitution mapping.

## P4. One Item Across Multiple POs

Example:

```text
Patient Cot with Mattress: Required 100
PO 217A: 60
PO 224A: 40
Ordered: 100
Pending: 0
```

## P5. Quantity Split Across PO Lines

Example:

```text
Saline Stand: Required 50
PO 220A: 30
PO 223A: 20
```

## P6. Same PO Item for Multiple Facilities

Use PO allocation grain; do not link using PO header alone.

## P7. Same Equipment Indented More Than Once

Use Indent Number, date, facility, department and remaining quantity. Manual allocation may be required.

## P8. PO Item Not Found in Current Indent

Search:

1. another indent for the same facility;
2. revised indent;
3. approved substitution;
4. another financial year;
5. package/component relationship.

If still unresolved, retain `PO Item Not Found in Indent`.

## P9. PO Against Not Required Item

Create mandatory review exception.

## P10. PO Date Before Indent or Approval

Create chronology exception.

## P11. PO Header and Line Amount Differ

Create financial data-quality exception; do not alter source values.

## P12. Duplicate PO Rows

Identify exact duplicates separately from legitimate repeated hospital allocations.

## P13. Same PO Number with Different Header Values

Flag `PO Header Conflict`.

## P14. PO Quantity Above Required Quantity

Flag `Potential Over-Order`; do not truncate automatically.

## P15. PO Quantity Below Required Quantity

Classify `Partially Ordered`.

---

# 13. Matching Score Model

```text
Institution compatibility:          30 points
Equipment / substitution:           35 points
RC or Tender relationship:          15 points
Quantity compatibility:             10 points
Vendor compatibility:                5 points
Date / financial-year compatibility: 5 points
Total:                              100 points
```

Mandatory controls:

- institution conflict prevents auto-link;
- critical technical conflict prevents exact-equipment classification;
- substitution requires approved mapping;
- multiple candidates require review regardless of high score;
- fuzzy matching may suggest but may not approve substitutions.

---

# 14. Lifecycle Status Catalogue

```text
Data Clarification Required
Institution Mapping Pending
Equipment Mapping Pending
Not Required
Pending Indent Review
Returned for Reprioritization
Approved - RC Check Pending
RC Verification Pending
Active RC - PO Pending
Tender Not Initiated
Tender in Progress
Pending BFC
RC Creation Pending
PO Pending
Partially Ordered
Fully Ordered
PO Issued - Supply Pending
Partially Supplied
Fully Supplied - QA Pending
Completed
Match Review Required
Rejected
Cancelled
```

Status calculations must follow priority rules. For example, an unresolved institution conflict must show `Institution Mapping Pending`, not `PO Pending`.

---

# 15. Exception Catalogue

```text
Required Column Unmapped
Header Row Not Detected
Mandatory Value Missing
Invalid Date
Invalid Quantity
Invalid Amount
Institution Not Mapped
Multiple Institution Matches
District Conflict
Equipment Not Mapped
Multiple Equipment Matches
Critical Technical Attribute Conflict
Vendor Not Mapped
Duplicate Indent Line
Duplicate PO Line
Duplicate Tender Item
Multiple RC Candidates
RC Validity Missing
No Active RC
Tender Required but Not Initiated
Tender Stage Missing
PO Item Not Found in Indent
Multiple PO Candidates
PO Linked to Not Required Item
PO Quantity Exceeds Required Quantity
PO Date Before Indent/Approval
PO Header Conflict
PO Header and Line Amount Mismatch
Approved Substitution Reference Missing
Package Component Review Required
Supply Status and Quantity Conflict
```

Each exception shall include severity, owner, status, resolution and timestamps.

---

# 16. Output Workbook

## 16.1 Output Location

```text
C:\VSCode Projects\Indent Tracker\Files\Output File\TGMSIDC_Indent_Lifecycle_<timestamp>.xlsx
```

Optional latest copy:

```text
TGMSIDC_Indent_Lifecycle_Latest.xlsx
```

## 16.2 Required Worksheets

### `01_Run_Summary`

Import batch, files, rows, validations and open exceptions.

### `02_Indent_Lifecycle`

One row per facility-wise Indent item. This is the principal management dataset.

```text
IndentID
IndentLineID
IndentNo
IndentDate
ASNumber
ASAmount
BudgetHead
HOD
InstitutionID
Hospital
District
Department
SourceItemName
EquipmentID
StandardItemName
ProcurementCategory
EquipmentType
RequiredQty
UnitOfMeasure
Prioritization
RCNumber
RCStatus
RCValidUpto
TenderRequired
TenderNo
TenderItemID
TenderStage
BFCStatus
PONumbers
POCount
ConfirmedOrderedQty
POPendQty
SuppliedQty
SupplyPendingQty
SupplyStatus
MatchType
MatchScore
ReviewStatus
CurrentLifecycleStatus
ExceptionCount
ApprovalReference
LastReviewedBy
LastReviewedOn
SourceFile
SourceSheet
SourceRow
```

### `03_PO_to_Indent`

One row per PO-line-to-Indent-line relationship.

### `04_RC_Status`

Indent-line-wise RC candidate and validity position.

### `05_Tender_Status`

Indent-line-wise Tender route, stage and outcome.

### `06_Match_Review`

All unresolved candidates and conflicts.

### `07_Exceptions`

All open and resolved validation/reconciliation exceptions.

### `08_Institution_Mapping`

Source hospital values, standard institution and scores.

### `09_Equipment_Mapping`

Source item values, standard equipment, technical attributes and scores.

### `10_Substitutions`

Approved alternative and technical-upgradation relationships.

### `11_Source_Lineage`

File, sheet, row, file hash and original record JSON.

### `12_Management_Summary`

Report-ready facility, district, HOD, item and lifecycle aggregates.

---

# 17. Output Formatting and Reporting Rules

- Every dataset shall be an Excel Table.
- No merged cells shall be used in source-like report sheets.
- Every table shall use a single header row.
- Filters shall be enabled.
- Top rows shall be frozen.
- Dates shall be true date values.
- Quantities and amounts shall be numeric.
- Amounts shall use Indian currency formatting.
- IDs shall remain text.
- Empty values shall remain blank.
- No formulas shall depend on source workbook paths.
- Each sheet shall have a clearly defined row grain.
- Detailed many-to-many links shall not be replaced by comma-separated text alone.
- `02_Indent_Lifecycle` may show consolidated PO numbers for convenience, while `03_PO_to_Indent` remains the authoritative PO linkage table.
- Output structures must be directly usable in PivotTables, Power Query and Power BI.

---

# 18. Management Reporting Use Cases

## Facility-Wise

```text
Total Indent Lines
Required / Not Required
Active RC
No RC
Tender Required
Tender Not Initiated
Tender in Progress
PO Issued
Fully Ordered
Partially Ordered
PO Pending
Unmatched PO Items
```

## Item-Wise

```text
Total Required Quantity Across Facilities
Facilities Requiring the Item
Active RC Coverage
Tender Pipeline
PO Quantity
Pending Quantity
Technical Substitutions
```

## Department-Wise

```text
ICU
Emergency
OBG / Labour Room
Operation Theatre
Radiology
Laboratory
Paediatrics / SNCU
Furniture
Linen
IT and Electronics
```

## Exception-Wise

```text
No RC
Tender Not Initiated
PO Not Found
PO Item Not in Indent
Multiple PO Candidates
Over-Order
Technical Conflict
Missing Approval Reference
```

---

# 19. Streamlit Screens

```text
Dashboard
Folder Scan
Workbook and Sheet Review
Column Mapping
Institution Mapping
Equipment Mapping
Vendor Mapping
RC / Tender Candidate Review
PO Match Review
Substitution Review
Exception Register
Reports and Export
```

Review actions:

```text
Confirm Match
Reject Match
Select Alternative Candidate
Allocate Quantity
Confirm Approved Substitution
Confirm Package Component
Mark Reference Pending
Keep Pending
Mark No Match
```

---

# 20. Implementation Plan

## Phase 1: Foundation, Week 1

- create project structure;
- configure paths;
- build logging and SQLite schema;
- build folder scanner and file hashing;
- create Streamlit shell.

## Phase 2: Excel Import and Mapping, Week 2

- workbook/sheet scan;
- header row detection;
- source-to-destination mapping;
- data-type conversion;
- lineage preservation;
- import validation.

## Phase 3: Master Data Matching, Week 3

- institution normalization and aliases;
- equipment normalization and technical attributes;
- vendor aliases;
- match review screens;
- saved mapping decisions.

## Phase 4: Reconciliation, Week 4

- Indent to RC;
- Indent to Tender;
- Indent to PO;
- many-to-many links;
- quantity allocation;
- status calculation.

## Phase 5: Exceptions and Substitutions, Week 5

- match-review workflow;
- approved substitutions;
- package components;
- exception lifecycle;
- audit log.

## Phase 6: Outputs and Pilot, Week 6

- detailed Excel output;
- management summary;
- AH Choppadandi pilot;
- DME/TVVP sample extension;
- user acceptance testing.

---

# 21. Pilot Acceptance Scenarios

The AH Choppadandi pilot must reproduce the following:

1. Monitor 5 Para Qty 9 linked to Multipara Monitor 7 Para Qty 9 under PO 214A as an approved technical upgradation.
2. Monitor 3 Para Qty 15 remains separately visible unless another approved link is confirmed.
3. Hospital Cot with Mattress Qty 100 reconciles through PO 217A Qty 60 and PO 224A Qty 40.
4. Saline Stand Qty 50 reconciles through PO 220A Qty 30 and PO 223A Qty 20.
5. CR Machine Qty 1 links to the CR system while imaging plates are treated as package components.
6. Probable furniture/instrument matches remain pending until reviewed.
7. PO items not identified in the current indent remain in the exception report.
8. PO header and line-amount inconsistencies are exposed without changing source values.
9. Every linkage traces back to source file, sheet and row.

---

# 22. Definition of Done

Version 1 is complete when:

- all configured folders can be scanned;
- all source workbooks can be mapped without hard-coded column names;
- facility and item aliases can be saved and reused;
- detailed RC, Tender and PO candidates are generated;
- quantity reconciliation supports split and combined procurement;
- substitutions and package components are handled explicitly;
- uncertain matches require review;
- every PO line is classified;
- the main output gives facility-wise and item-wise lifecycle visibility;
- the output is immediately usable for reports;
- all results retain immutable source lineage.

---

# 23. Remaining Product Owner Decisions

1. Identify the exact worksheets to process in each workbook.
2. Confirm whether all worksheets should be scanned automatically.
3. Confirm support for legacy `.xls` files.
4. Provide or approve creation of the Institution Master.
5. Provide or approve creation of the Equipment Master.
6. Identify users authorized to confirm matches and substitutions.
7. Confirm whether approval references may initially be marked `Reference Pending`.
8. Confirm whether SQLite single-machine pilot or SQL Server shared pilot is required.
