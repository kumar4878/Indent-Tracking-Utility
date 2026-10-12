from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz

from cleaning_engine import (
    extract_attribute_tags,
    extract_keyword_tokens,
    is_blank,
    normalize_lookup_key,
    normalize_whitespace,
)
from database_service import ReconciliationDatabase
from models import LifecycleRecord, POAllocationRecord


@dataclass(slots=True)
class ReconciliationSummary:
    lifecycle_rows: int
    allocation_rows: int


def _load_alias_lookup(mapping_rules: Dict[str, Any]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    aliases = mapping_rules.get("approved_aliases", {})
    for alias, canonical in aliases.items():
        lookup[normalize_lookup_key(alias)] = normalize_whitespace(canonical)
        lookup[normalize_lookup_key(canonical)] = normalize_whitespace(canonical)
    return lookup


def _load_probable_pairs(mapping_rules: Dict[str, Any]) -> set:
    """Human-curated 'worth a second look' pairs (e.g. 'Mini surgery set' vs
    'Minor surgical instrument set') that generic fuzzy text scoring either
    misses entirely or scores unreliably. Unlike approved_aliases, these are
    NEVER auto-confirmed - they only guarantee the pair surfaces as a
    Probable Match candidate for human review.
    """
    pairs = mapping_rules.get("probable_aliases", {})
    return {frozenset({normalize_lookup_key(a), normalize_lookup_key(b)}) for a, b in pairs.items()}


def _load_keyword_guards(mapping_rules: Dict[str, Any]) -> Tuple[set, Dict[str, Any]]:
    """Config-driven guards that stop two semantically different items (e.g. a
    weighing scale vs. an ECG machine) from being accepted as a text-similarity
    match just because they share a generic word like "machine". Returns
    (generic_stopwords, attribute_keyword_map).
    """
    stopwords = {str(word).lower() for word in mapping_rules.get("generic_stopwords", [])}
    attribute_map = mapping_rules.get("attribute_keyword_map", {})
    return stopwords, attribute_map


def _shares_core_keyword(source_name: Any, candidate_name: Any, stopwords: set) -> bool:
    """Require at least one meaningful (non-generic) keyword in common. If
    either side has no meaningful keywords at all (very short/sparse names),
    don't block on this check - fall back to the fuzzy score alone.
    """
    source_tokens = extract_keyword_tokens(source_name, stopwords)
    candidate_tokens = extract_keyword_tokens(candidate_name, stopwords)
    if not source_tokens or not candidate_tokens:
        return True
    return bool(source_tokens & candidate_tokens)


def _has_attribute_conflict(source_name: Any, candidate_name: Any, attribute_map: Dict[str, Any]) -> bool:
    """True when both texts mention the same critical-attribute category
    (mobility, patient type, scale, operation, configuration, material) but
    with different tags (e.g. "Adult" vs "Paediatric", "Portable" vs "Fixed").
    """
    if not attribute_map:
        return False
    source_tags = extract_attribute_tags(source_name, attribute_map)
    if not source_tags:
        return False
    candidate_tags = extract_attribute_tags(candidate_name, attribute_map)
    for category, tag in source_tags.items():
        other_tag = candidate_tags.get(category)
        if other_tag and other_tag != tag:
            return True
    return False


def _normalize_item_name(value: Any, alias_lookup: Dict[str, str]) -> str:
    text = normalize_whitespace(value)
    if not text or text.casefold() in {"nan", "none", "null", "<na>"}:
        return ""
    lookup_key = normalize_lookup_key(text)
    return normalize_lookup_key(alias_lookup.get(lookup_key, text))


def _forced_probable_candidates(source_name: str, candidates: pd.DataFrame, probable_pairs: set) -> pd.DataFrame:
    if not probable_pairs or candidates.empty:
        return candidates.iloc[0:0].copy()
    query_raw_key = normalize_lookup_key(source_name)
    mask = candidates["source_item_name"].map(
        lambda other: frozenset({query_raw_key, normalize_lookup_key(other)}) in probable_pairs
    )
    forced = candidates.loc[mask].copy()
    if not forced.empty:
        forced["match_score"] = None
    return forced


def _prepare_candidates(frame: pd.DataFrame, id_column: str, name_column: str, alias_lookup: Dict[str, str]) -> pd.DataFrame:
    candidates = frame.copy()
    candidates[name_column] = candidates[name_column].fillna("").astype(str).map(normalize_whitespace)
    candidates["normalized_key"] = candidates[name_column].map(lambda value: _normalize_item_name(value, alias_lookup))
    candidates = candidates[candidates["normalized_key"].notna() & (candidates["normalized_key"] != "")]
    candidates = candidates[candidates["normalized_key"].str.lower() != "nan"]
    return candidates.drop_duplicates()


def _best_fuzzy_matches(
    query_key: str,
    candidates: pd.DataFrame,
    id_column: str,
    name_column: str,
    threshold: int,
    max_candidates: int = 3,
    score_margin: int = 5,
    query_raw_name: str = "",
    keyword_stopwords: Optional[set] = None,
    attribute_map: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    if not query_key or candidates.empty:
        empty = candidates.iloc[0:0].copy()
        empty["match_score"] = pd.Series(dtype=float)
        return empty

    keyword_stopwords = keyword_stopwords or set()
    scored_rows: List[Tuple[int, int]] = []
    for index, candidate_key in candidates["normalized_key"].items():
        score = max(
            fuzz.ratio(query_key, candidate_key),
            fuzz.token_sort_ratio(query_key, candidate_key),
            fuzz.partial_ratio(query_key, candidate_key),
        )
        if score < threshold:
            continue
        candidate_raw_name = candidates.loc[index, name_column]
        # A high text score alone is not enough: two items must share at least
        # one meaningful keyword, and must not conflict on a critical attribute
        # (mobility, patient type, scale, etc.), or they are rejected outright
        # regardless of score (e.g. "Weighing machine adult" vs "12 Channel ECG
        # Machine" sharing only the generic word "machine").
        if not _shares_core_keyword(query_raw_name, candidate_raw_name, keyword_stopwords):
            continue
        if _has_attribute_conflict(query_raw_name, candidate_raw_name, attribute_map or {}):
            continue
        scored_rows.append((index, int(score)))

    if not scored_rows:
        empty = candidates.iloc[0:0].copy()
        empty["match_score"] = pd.Series(dtype=float)
        return empty

    scored = candidates.loc[[index for index, _ in scored_rows]].copy()
    scored["match_score"] = [score for _, score in scored_rows]
    scored = scored.sort_values(["match_score", id_column], ascending=[False, True])
    top_score = int(scored.iloc[0]["match_score"])
    scored = scored[scored["match_score"] >= top_score - score_margin]
    return scored.head(max_candidates)


def _score_exact_and_fuzzy_matches(
    query_key: str,
    candidates: pd.DataFrame,
    id_column: str,
    name_column: str,
    threshold: int,
    query_raw_name: str = "",
    keyword_stopwords: Optional[set] = None,
    attribute_map: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    if not query_key or candidates.empty:
        empty = candidates.iloc[0:0].copy()
        empty["match_score"] = pd.Series(dtype=float)
        return empty

    exact_matches = candidates[candidates["normalized_key"] == query_key].copy()
    if not exact_matches.empty:
        # Even an exact normalized-text match is not confirmed if a critical
        # attribute conflicts (PRD I3: "confirmed only when critical attributes
        # do not conflict").
        if attribute_map:
            conflict_mask = exact_matches[name_column].map(
                lambda other: _has_attribute_conflict(query_raw_name, other, attribute_map)
            )
            exact_matches = exact_matches.loc[~conflict_mask]
        if not exact_matches.empty:
            exact_matches["match_score"] = 100
            return exact_matches.sort_values(["match_score", id_column], ascending=[False, True])

    return _best_fuzzy_matches(
        query_key,
        candidates,
        id_column,
        name_column,
        threshold,
        query_raw_name=query_raw_name,
        keyword_stopwords=keyword_stopwords,
        attribute_map=attribute_map,
    )


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        text = normalize_whitespace(value).replace(",", "")
        if not text:
            return 0.0
        number = float(text)
        return number if math.isfinite(number) else 0.0
    except Exception:
        return 0.0


def _normalize_compare(value: Any) -> str:
    text = normalize_whitespace(value).casefold()
    if text in {"", "nan", "none", "null", "<na>", "-", "n/a", "na"}:
        return ""
    return text


def _facility_key(value: Any) -> str:
    """Normalize presentation, not geography; never fuzzy-match hospital names."""
    text = _normalize_compare(value)
    # A department suffix identifies a unit of the same hospital, not a new hospital.
    text = re.split(r"\b(?:dept\.?|department)\s+of\b", text, maxsplit=1)[0]
    text = re.sub(r"\b(?:area\s+hospital|a\s*\.\s*h\.?)\b", "ah", text)
    text = re.sub(r"\b(?:district\s+hospital|d\s*\.\s*h\.?)\b", "dh", text)
    text = re.sub(r"\bcommunity\s+health\s+cent(?:er|re)\b", "chc", text)
    text = re.sub(r"\bgovernment\s+medical\s+college\b", "gmc", text)
    return normalize_lookup_key(text)


def _district_key(value: Any) -> str:
    return normalize_lookup_key(re.sub(r"\b(?:district|dist\.?)\b", "", _normalize_compare(value)))


def _po_facility_matches(indent_institution: Any, indent_district: Any, po_location: Any, po_district: Any) -> bool:
    institution = _facility_key(indent_institution)
    location = _facility_key(po_location)
    district = _district_key(indent_district)
    target_district = _district_key(po_district)
    # Unknown identity must not act as a wildcard. Conflicting districts block links.
    return bool(
        institution and location and institution == location
        and district and target_district and district == target_district
    )


def _po_item_matches(
    key: str,
    source_name: str,
    candidates: pd.DataFrame,
    threshold: int,
    attribute_map: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Confirm exact/approved aliases or very close whole names, not substrings.

    Numeric specification differences (e.g. "100mA" vs "200mA") cannot be
    overridden by a high text score for a generic fuzzy match. The only
    exception is when an approved alias explicitly transformed one of the two
    labels into the other's canonical form (e.g. an approved 7-Para monitor
    substituting for a 5-Para requirement) -- that is a human-reviewed
    statement of equivalence, so it may bypass the numeric guard. Two labels
    that merely *normalize* to the same compact key without any alias
    involvement (e.g. "MRI 1.5 Tesla" and "MRI 15 Tesla" both collapse to
    "mri15tesla" once punctuation is stripped) must NOT bypass the guard.
    Non-numeric critical attributes (mobility, patient type, scale, operation,
    configuration, material) follow the same rule.
    """
    scored = candidates.copy()
    if not key or scored.empty:
        scored = scored.iloc[0:0].copy()
        scored["match_score"] = pd.Series(index=scored.index, dtype=float)
        return scored
    scored["match_score"] = scored["normalized_key"].map(lambda other: fuzz.ratio(key, other))
    exact = scored["normalized_key"] == key
    # Numeric specification differences cannot be overridden by a high text score
    # for anything that is not an exact/alias match. Read numbers from the original
    # labels: compact normalized keys lose decimal points and separators.
    numbers = re.findall(r"\d+(?:\.\d+)?", source_name)
    numeric_safe = scored["source_item_name"].map(lambda other: re.findall(r"\d+(?:\.\d+)?", other) == numbers)
    raw_indent_key = normalize_lookup_key(source_name)
    alias_applied_for_indent = raw_indent_key != key
    alias_applied_for_candidate = scored["source_item_name"].map(normalize_lookup_key) != scored["normalized_key"]
    alias_approved = alias_applied_for_indent | alias_applied_for_candidate
    attribute_conflict = scored["source_item_name"].map(
        lambda other: _has_attribute_conflict(source_name, other, attribute_map or {})
    )
    attribute_safe = ~attribute_conflict | alias_approved
    compatible = (exact & (numeric_safe | alias_approved) & attribute_safe) | (
        ~exact & numeric_safe & attribute_safe & (scored["match_score"] >= threshold)
    )
    return scored.loc[compatible].sort_values(["match_score", "po_line_id"], ascending=[False, True])


def _allocation_status(allocated_qty: float, remaining_required_qty: float, ordered_qty: float) -> str:
    if allocated_qty <= 0:
        return "Unallocated"
    if remaining_required_qty <= 0 and ordered_qty > allocated_qty:
        return "Partially Allocated"
    if remaining_required_qty <= 0:
        return "Allocated"
    return "Partially Allocated"


def _compute_confidence_score(
    *,
    po_candidate_count: int,
    institution_name: Any,
    equipment_match_score: float,
    has_rc_or_tender_match: bool,
    required_qty: float,
    total_allocated_qty: float,
    matched_po_ids: List[int],
    po_lookup: pd.DataFrame,
) -> float:
    """Weighted composite confidence score (0-100), additive to - and never a
    replacement for - the text-similarity `match_score` that drives the
    Confirmed/Probable/Not-Matched classification (see PRD section 13):
      Institution (30) + Equipment (35) + RC/Tender relationship (15)
      + Quantity (10) + Vendor (5) + Date (5).
    Vendor/Date are scored on whether a concrete, accountable PO allocation
    exists (vendor is only ever known on the PO side - indents carry no
    vendor of their own) rather than a direct text comparison, since no
    vendor/date field exists on the indent side of the data model today.
    """
    if po_candidate_count > 0:
        institution_score = 30.0
    elif not is_blank(institution_name):
        institution_score = 15.0
    else:
        institution_score = 0.0

    equipment_score = 35.0 * max(min(equipment_match_score, 100.0), 0.0) / 100.0
    relationship_score = 15.0 if has_rc_or_tender_match else 0.0

    if required_qty > 0:
        quantity_score = 10.0 * max(min(total_allocated_qty / required_qty, 1.0), 0.0)
    else:
        quantity_score = 0.0

    vendor_score = 5.0 if matched_po_ids else 0.0
    date_score = 0.0
    if matched_po_ids and not po_lookup.empty:
        for po_line_id in matched_po_ids:
            if po_line_id in po_lookup.index and not is_blank(po_lookup.loc[po_line_id].get("po_date")):
                date_score = 5.0
                break

    return round(institution_score + equipment_score + relationship_score + quantity_score + vendor_score + date_score, 2)


def _attach_package_components(
    config: Dict[str, Any],
    po: pd.DataFrame,
    allocation_rows: List[POAllocationRecord],
    lifecycle_rows: List[LifecycleRecord],
) -> List[POAllocationRecord]:
    """Attach accessory/component PO lines (e.g. imaging plates bundled with a
    CR machine) to the indent line whose anchor item was already confirmed, so
    the accessories are not reported as orphan PO lines. This never changes
    required/allocated quantity accounting; it only records the linkage.
    """
    if not config or po.empty:
        return []

    allocated_po_ids = {allocation.po_line_id for allocation in allocation_rows}
    allocation_by_po_id = {allocation.po_line_id: allocation for allocation in allocation_rows}
    lifecycle_by_indent_line = {record.indent_line_id: record for record in lifecycle_rows}
    extra_allocations: List[POAllocationRecord] = []

    for po_no, group in config.items():
        anchor_text = normalize_lookup_key(group.get("anchor", ""))
        component_texts = [normalize_lookup_key(text) for text in group.get("components", [])]
        po_group = po[po["po_no"].astype(str) == str(po_no)]
        if po_group.empty:
            continue
        anchor_rows = po_group[po_group["source_item_name"].astype(str).map(normalize_lookup_key) == anchor_text]
        if anchor_rows.empty:
            continue
        anchor_po_id = int(anchor_rows.iloc[0]["po_line_id"])
        anchor_allocation = allocation_by_po_id.get(anchor_po_id)
        if anchor_allocation is None:
            continue  # the anchor itself was not confirmed; do not attach components speculatively
        lifecycle_record = lifecycle_by_indent_line.get(anchor_allocation.indent_line_id)

        for component_text in component_texts:
            component_rows = po_group[po_group["source_item_name"].astype(str).map(normalize_lookup_key) == component_text]
            if component_rows.empty:
                continue
            component_po_id = int(component_rows.iloc[0]["po_line_id"])
            if component_po_id in allocated_po_ids:
                continue
            component_row = component_rows.iloc[0]
            component_qty = _to_float(component_row.get("ordered_qty"))
            extra_allocations.append(
                POAllocationRecord(
                    batch_id=anchor_allocation.batch_id,
                    lifecycle_id=None,
                    indent_line_id=anchor_allocation.indent_line_id,
                    indent_header_id=anchor_allocation.indent_header_id,
                    po_line_id=component_po_id,
                    allocation_order=len(allocation_rows) + len(extra_allocations) + 1,
                    source_file=str(component_row.get("source_file", "")),
                    source_sheet=str(component_row.get("source_sheet", "")),
                    source_row=int(_to_float(component_row.get("source_row"))),
                    source_item_name=str(component_row.get("source_item_name", "")),
                    po_no=str(component_row.get("po_no", "")),
                    po_date=str(component_row.get("po_date", "")),
                    ordered_qty=f"{component_qty:g}",
                    allocated_qty=f"{component_qty:g}",
                    remaining_indent_qty=anchor_allocation.remaining_indent_qty,
                    allocation_status="Package Component",
                    raw_payload={
                        "package_component_of": anchor_allocation.source_item_name,
                        "po_row": component_row.to_dict(),
                    },
                )
            )
            allocated_po_ids.add(component_po_id)
            if lifecycle_record is not None:
                matched_ids = json.loads(lifecycle_record.matched_po_ids or "[]")
                matched_ids.append(component_po_id)
                lifecycle_record.matched_po_ids = json.dumps(matched_ids)

    return extra_allocations


def _suggest_generic_package_components(
    mapping_rules: Dict[str, Any],
    po: pd.DataFrame,
    allocation_rows: List[POAllocationRecord],
    lifecycle_rows: List[LifecycleRecord],
) -> None:
    """For any confirmed anchor PO line, flag unclaimed sibling lines sharing
    its `po_no` as *suggested* (never auto-confirmed) package components when
    they either share a non-generic keyword with the anchor's item name or
    contain a known component-hint keyword (e.g. "plate", "cassette",
    "accessory"). This generalizes the curated `package_components` config
    (I8/I9) to items that were never explicitly listed, without ever changing
    required/allocated quantity accounting - mutates each lifecycle record's
    `raw_payload["suggested_components"]` in place for display only.
    """
    if po.empty or not lifecycle_rows:
        return

    stopwords, _ = _load_keyword_guards(mapping_rules)
    component_hints = {str(hint).lower() for hint in mapping_rules.get("component_keyword_hints", [])}
    if not component_hints and not stopwords:
        return

    lifecycle_by_indent_line = {record.indent_line_id: record for record in lifecycle_rows}

    # Anything already visible elsewhere (confirmed, package component, or a
    # probable candidate for any indent line) is excluded so the same PO line
    # is never suggested here in addition to already being shown there.
    claimed_po_ids = {allocation.po_line_id for allocation in allocation_rows}
    for record in lifecycle_rows:
        for candidate in record.raw_payload.get("po_review_candidates", []) or []:
            claimed_po_ids.add(int(candidate["po_line_id"]))

    confirmed_allocations = [a for a in allocation_rows if a.allocation_status != "Package Component"]
    po_by_line_id = po.set_index("po_line_id")

    for anchor_allocation in confirmed_allocations:
        anchor_po_id = anchor_allocation.po_line_id
        if anchor_po_id not in po_by_line_id.index:
            continue
        anchor_name = str(po_by_line_id.loc[anchor_po_id, "source_item_name"])
        anchor_tokens = extract_keyword_tokens(anchor_name, stopwords)
        po_no = str(po_by_line_id.loc[anchor_po_id, "po_no"])
        siblings = po[(po["po_no"].astype(str) == po_no) & (po["po_line_id"] != anchor_po_id)]

        lifecycle_record = lifecycle_by_indent_line.get(anchor_allocation.indent_line_id)
        if lifecycle_record is None:
            continue

        for sibling in siblings.itertuples():
            sibling_po_id = int(getattr(sibling, "po_line_id"))
            if sibling_po_id in claimed_po_ids:
                continue
            sibling_name = str(getattr(sibling, "source_item_name"))
            sibling_tokens = extract_keyword_tokens(sibling_name, stopwords)
            has_hint = bool(sibling_tokens & component_hints)
            shares_keyword = bool(anchor_tokens and sibling_tokens and (anchor_tokens & sibling_tokens))
            if not has_hint and not shares_keyword:
                continue
            lifecycle_record.raw_payload.setdefault("suggested_components", []).append(
                {
                    "po_line_id": sibling_po_id,
                    "po_no": po_no,
                    "source_item_name": sibling_name,
                    "ordered_qty": getattr(sibling, "ordered_qty"),
                    "suggestion_reason": "component_keyword_hint" if has_hint else "shared_keyword_with_anchor",
                    "status": "Suggested Component - Confirmation Required",
                }
            )
            claimed_po_ids.add(sibling_po_id)


def _detect_po_header_amount_mismatches(database: ReconciliationDatabase, tolerance: float) -> List[Dict[str, Any]]:
    """Flag PO numbers whose header gross amount disagrees with the sum of its
    own line totals -- a data-quality problem in the source workbook, independent
    of indent matching."""
    po = database.fetch_dataframe("SELECT po_line_id, batch_id, po_no, source_file, source_sheet, gross_amount, total_amount FROM po_lines")
    if po.empty:
        return []
    po["gross_amount_f"] = po["gross_amount"].map(_to_float)
    po["total_amount_f"] = po["total_amount"].map(_to_float)
    mismatches: List[Dict[str, Any]] = []
    for po_no, group in po.groupby("po_no"):
        if not str(po_no).strip():
            continue
        header_amount = float(group["gross_amount_f"].iloc[0])
        line_sum = float(group["total_amount_f"].sum())
        if abs(header_amount - line_sum) > tolerance:
            mismatches.append(
                {
                    "po_no": po_no,
                    "batch_id": group["batch_id"].iloc[0],
                    "header_amount": header_amount,
                    "line_sum": line_sum,
                    "source_file": group["source_file"].iloc[0],
                    "source_sheet": group["source_sheet"].iloc[0],
                }
            )
    return mismatches


def _detect_unmatched_po_lines(
    database: ReconciliationDatabase,
    lifecycle_rows: List[LifecycleRecord],
    allocation_rows: List[POAllocationRecord],
) -> List[Dict[str, Any]]:
    """Find PO lines, at a hospital/district that does have indent data, which
    were never confirmed, never attached as a package component, and never even
    surfaced as a probable-match candidate for any indent line. These are
    genuinely absent from the current indent (e.g. furniture ordered outside the
    indent list) and should be reported, not silently dropped."""
    po = database.fetch_dataframe(
        "SELECT po_line_id, batch_id, po_no, source_file, source_sheet, source_row, source_item_name, location, district, ordered_qty FROM po_lines"
    )
    indent_headers = database.fetch_dataframe("SELECT institution_name, district FROM indent_headers")
    if po.empty or indent_headers.empty:
        return []

    touched_po_ids = {allocation.po_line_id for allocation in allocation_rows}
    for record in lifecycle_rows:
        touched_po_ids.update(json.loads(record.matched_po_ids or "[]"))
        for review in (record.raw_payload or {}).get("po_review_candidates", []):
            po_id = review.get("po_line_id")
            if po_id is not None:
                touched_po_ids.add(int(po_id))
        for suggestion in (record.raw_payload or {}).get("suggested_components", []):
            po_id = suggestion.get("po_line_id")
            if po_id is not None:
                touched_po_ids.add(int(po_id))

    in_scope_facilities = {
        (_facility_key(row.institution_name), _district_key(row.district)) for row in indent_headers.itertuples()
    }

    orphans: List[Dict[str, Any]] = []
    for row in po.itertuples():
        if int(row.po_line_id) in touched_po_ids:
            continue
        facility = (_facility_key(row.location), _district_key(row.district))
        if facility not in in_scope_facilities:
            continue
        orphans.append(
            {
                "po_line_id": int(row.po_line_id),
                "batch_id": row.batch_id,
                "po_no": row.po_no,
                "source_item_name": row.source_item_name,
                "location": row.location,
                "district": row.district,
                "ordered_qty": row.ordered_qty,
                "source_file": row.source_file,
                "source_sheet": row.source_sheet,
                "source_row": row.source_row,
            }
        )
    return orphans


def build_lifecycle_rows(database: ReconciliationDatabase, mapping_rules: Dict[str, Any]) -> Tuple[List[LifecycleRecord], List[POAllocationRecord]]:
    alias_lookup = _load_alias_lookup(mapping_rules)
    probable_pairs = _load_probable_pairs(mapping_rules)
    keyword_stopwords, attribute_map = _load_keyword_guards(mapping_rules)
    item_threshold = int(mapping_rules.get("item_name_threshold", 95))
    probable_threshold = int(mapping_rules.get("item_probable_threshold", 70))

    indent = database.fetch_dataframe("SELECT * FROM indent_lines ORDER BY indent_line_id")
    indent_headers = database.fetch_dataframe("SELECT indent_header_id, institution_name, district FROM indent_headers")
    rc = database.fetch_dataframe("SELECT rc_item_id, source_item_name, vendor_name, unit_rate_incl_gst, rc_group_no FROM rc_items")
    tender = database.fetch_dataframe("SELECT tender_item_id, source_item_name, tender_stage, tender_no FROM tender_items")
    po = database.fetch_dataframe("SELECT po_line_id, source_file, source_sheet, source_row, source_item_name, ordered_qty, po_no, po_date, location, district FROM po_lines")

    if indent.empty:
        return [], []

    if not indent_headers.empty:
        indent = indent.merge(indent_headers, on="indent_header_id", how="left", suffixes=("", "_header"))
    else:
        indent["institution_name"] = ""
        indent["district"] = ""

    rc_candidates = _prepare_candidates(rc, "rc_item_id", "source_item_name", alias_lookup)
    tender_candidates = _prepare_candidates(tender, "tender_item_id", "source_item_name", alias_lookup)
    po_candidates = _prepare_candidates(po, "po_line_id", "source_item_name", alias_lookup)
    po_lookup = po.set_index("po_line_id") if not po.empty else pd.DataFrame()
    indent["normalized_key"] = indent["normalized_item_name"].apply(lambda value: _normalize_item_name(value, alias_lookup))

    # Cache facility-scoped matches once. Prioritize exact items before fuzzy ones
    # so an earlier approximate name cannot consume a later exact item's PO.
    facility_cache: Dict[Tuple[str, str], pd.DataFrame] = {}
    po_matches_by_line: Dict[int, pd.DataFrame] = {}
    for _, row in indent.iterrows():
        facility = (_facility_key(row.get("institution_name")), _district_key(row.get("district")))
        if facility not in facility_cache:
            mask = [
                _po_facility_matches(row.get("institution_name"), row.get("district"), candidate.location, candidate.district)
                for candidate in po_candidates.itertuples()
            ]
            facility_cache[facility] = po_candidates.loc[pd.Series(mask, index=po_candidates.index, dtype=bool)]
        candidates = facility_cache[facility]
        line_id = int(row["indent_line_id"])
        matches = _po_item_matches(row["normalized_key"], str(row["source_item_name"]), candidates, item_threshold, attribute_map)
        po_matches_by_line[line_id] = matches

    # A PO line is a single physical row in the register: it must never be
    # confirmed-or-suggested against more indent items than it actually has
    # line rows for. Confirmed matches claim a PO line globally (across ALL
    # indent rows, not just the current one) before any probable candidates
    # are considered.
    globally_confirmed_po_ids: set = set()
    for matches in po_matches_by_line.values():
        if not matches.empty:
            globally_confirmed_po_ids.update(int(po_id) for po_id in matches["po_line_id"])

    indent["po_priority"] = indent["indent_line_id"].map(
        lambda line_id: po_matches_by_line[line_id]["match_score"].max() if not po_matches_by_line[line_id].empty else 0
    )
    indent = indent.sort_values(["po_priority", "indent_line_id"], ascending=[False, True])
    remaining_po_qty = {int(row.po_line_id): max(_to_float(row.ordered_qty), 0.0) for row in po.itertuples()}

    # Probable candidates are assigned in priority order (highest-confidence
    # confirmed rows processed first) so a PO line already claimed as a
    # probable candidate for one indent row cannot be re-suggested to a later,
    # lower-priority row. This does not limit how many *different* PO lines one
    # indent row can draw from (legitimate multi-vendor quantity splits, P4/P5
    # are untouched - this only caps reuse of the SAME po_line_id).
    claimed_probable_po_ids: set = set()

    lifecycle_rows: List[LifecycleRecord] = []
    allocation_rows: List[POAllocationRecord] = []
    for _, indent_row in indent.iterrows():
        key = indent_row["normalized_key"]
        source_name = str(indent_row["source_item_name"])
        rc_matches = _score_exact_and_fuzzy_matches(
            key, rc_candidates, "rc_item_id", "source_item_name", probable_threshold,
            query_raw_name=source_name, keyword_stopwords=keyword_stopwords, attribute_map=attribute_map,
        )
        tender_matches = _score_exact_and_fuzzy_matches(
            key, tender_candidates, "tender_item_id", "source_item_name", probable_threshold,
            query_raw_name=source_name, keyword_stopwords=keyword_stopwords, attribute_map=attribute_map,
        )
        po_matches = po_matches_by_line[int(indent_row["indent_line_id"])]

        facility = (_facility_key(indent_row.get("institution_name")), _district_key(indent_row.get("district")))
        facility_candidates = facility_cache[facility]
        excluded_po_ids = globally_confirmed_po_ids | claimed_probable_po_ids
        available_candidates = facility_candidates.loc[~facility_candidates["po_line_id"].isin(excluded_po_ids)]
        probable = _score_exact_and_fuzzy_matches(
            key, available_candidates, "po_line_id", "source_item_name", probable_threshold,
            query_raw_name=source_name, keyword_stopwords=keyword_stopwords, attribute_map=attribute_map,
        )
        forced = _forced_probable_candidates(source_name, available_candidates, probable_pairs)
        forced = forced.loc[~forced["po_line_id"].isin(probable["po_line_id"])]
        if not forced.empty:
            probable = pd.concat([probable, forced], ignore_index=False)
        if not probable.empty:
            claimed_probable_po_ids.update(int(po_id) for po_id in probable["po_line_id"])
        po_reviews = probable

        rc_match_key = rc_matches.iloc[0]["normalized_key"] if not rc_matches.empty else ""
        tender_match_key = tender_matches.iloc[0]["normalized_key"] if not tender_matches.empty else ""
        po_match_key = po_matches.iloc[0]["normalized_key"] if not po_matches.empty else ""

        required_qty = _to_float(indent_row.get("required_qty"))
        matched_po_ids: List[int] = []
        total_allocated_qty = 0.0
        total_candidate_qty = sum(remaining_po_qty[int(po_id)] for po_id in po_matches["po_line_id"])
        remaining_required_qty = required_qty

        if not po_matches.empty and not po_lookup.empty:
            for po_row in po_matches.itertuples(index=False):
                po_line_id = int(getattr(po_row, "po_line_id"))
                if po_line_id not in po_lookup.index:
                    continue
                ordered_qty = _to_float(po_lookup.loc[po_line_id, "ordered_qty"])
                allocation_qty = min(max(remaining_required_qty, 0.0), remaining_po_qty[po_line_id])
                allocation_status = _allocation_status(allocation_qty, remaining_required_qty - allocation_qty, ordered_qty)
                if allocation_qty > 0:
                    remaining_po_qty[po_line_id] -= allocation_qty
                    matched_po_ids.append(po_line_id)
                    total_allocated_qty += allocation_qty
                    remaining_required_qty = max(remaining_required_qty - allocation_qty, 0.0)
                    allocation_rows.append(
                        POAllocationRecord(
                            batch_id=str(indent_row["batch_id"]),
                            lifecycle_id=None,
                            indent_line_id=int(indent_row["indent_line_id"]),
                            indent_header_id=int(indent_row["indent_header_id"]),
                            po_line_id=po_line_id,
                            allocation_order=len(matched_po_ids),
                            source_file=str(po_lookup.loc[po_line_id, "source_file"]) if "source_file" in po_lookup.columns else "",
                            source_sheet=str(po_lookup.loc[po_line_id, "source_sheet"]) if "source_sheet" in po_lookup.columns else "",
                            source_row=int(po_lookup.loc[po_line_id, "source_row"]) if "source_row" in po_lookup.columns else 0,
                            source_item_name=str(po_lookup.loc[po_line_id, "source_item_name"]) if "source_item_name" in po_lookup.columns else "",
                            po_no=str(po_lookup.loc[po_line_id, "po_no"]) if "po_no" in po_lookup.columns else "",
                            po_date=str(po_lookup.loc[po_line_id, "po_date"]) if "po_date" in po_lookup.columns else "",
                            ordered_qty=f"{ordered_qty:g}",
                            allocated_qty=f"{allocation_qty:g}",
                            remaining_indent_qty=f"{remaining_required_qty:g}",
                            allocation_status=allocation_status,
                            raw_payload={
                                "indent_row": indent_row.to_dict(),
                                "po_row": po_lookup.loc[po_line_id].to_dict(),
                            },
                        )
                    )
                if remaining_required_qty <= 0:
                    break
        po_pending_qty = max(required_qty - total_allocated_qty, 0.0)

        if total_allocated_qty > 0 and required_qty > 0 and total_allocated_qty >= required_qty:
            current_status = "Fully Ordered"
        elif total_allocated_qty > 0 and remaining_required_qty > 0:
            current_status = "Partially Ordered"
        elif not rc_matches.empty:
            current_status = "Active RC - PO Pending"
        elif not tender_matches.empty:
            current_status = "Tender in Progress"
        else:
            current_status = "Match Review Required"

        match_type = "No Match"
        match_score = 0.0
        review_status = "Review Required"
        if not rc_matches.empty or not tender_matches.empty or not po_matches.empty:
            best_score = 0
            if not rc_matches.empty:
                best_score = max(best_score, int(rc_matches.iloc[0].get("match_score", 100)))
            if not tender_matches.empty:
                best_score = max(best_score, int(tender_matches.iloc[0].get("match_score", 100)))
            if not po_matches.empty:
                best_score = max(best_score, int(po_matches.iloc[0].get("match_score", 100)))
            match_score = float(best_score)
            if key in rc_matches["normalized_key"].tolist() or key in tender_matches["normalized_key"].tolist() or key in po_matches["normalized_key"].tolist():
                match_type = "Exact Normalized Name Match"
                review_status = "Auto Linked" if best_score >= item_threshold else "Review Required"
            elif best_score >= item_threshold:
                match_type = "Approved Alias Match"
                review_status = "Auto Linked"
            else:
                match_type = "Probable Match"
                review_status = "Review Required"
        if total_candidate_qty > required_qty > 0:
            review_status = "Review Required"
        if not po_reviews.empty or (not po_matches.empty and po_pending_qty > 0):
            review_status = "Review Required"

        confidence_score = _compute_confidence_score(
            po_candidate_count=int(len(po_matches) + len(po_reviews)),
            institution_name=indent_row.get("institution_name"),
            equipment_match_score=match_score,
            has_rc_or_tender_match=not rc_matches.empty or not tender_matches.empty,
            required_qty=required_qty,
            total_allocated_qty=total_allocated_qty,
            matched_po_ids=matched_po_ids,
            po_lookup=po_lookup,
        )

        lifecycle_rows.append(
            LifecycleRecord(
                batch_id=str(indent_row["batch_id"]),
                indent_line_id=int(indent_row["indent_line_id"]),
                indent_header_id=int(indent_row["indent_header_id"]),
                file_id=int(indent_row["file_id"]),
                sheet_id=int(indent_row["sheet_id"]),
                source_file=str(indent_row["source_file"]),
                source_sheet=str(indent_row["source_sheet"]),
                source_row=int(indent_row["source_row"]),
                source_item_name=str(indent_row["source_item_name"]),
                normalized_item_name=key,
                required_qty=str(indent_row["required_qty"]),
                rc_candidate_count=int(len(rc_matches)),
                tender_candidate_count=int(len(tender_matches)),
                po_candidate_count=int(len(po_matches) + len(po_reviews)),
                matched_rc_ids=json.dumps(rc_matches["rc_item_id"].astype(int).tolist()),
                matched_tender_ids=json.dumps(tender_matches["tender_item_id"].astype(int).tolist()),
                matched_po_ids=json.dumps(matched_po_ids),
                confirmed_ordered_qty=f"{total_allocated_qty:g}",
                po_pending_qty=f"{po_pending_qty:g}",
                current_lifecycle_status=current_status,
                match_type=match_type,
                match_score=match_score,
                review_status=review_status,
                exception_count=0,
                confidence_score=confidence_score,
                raw_payload={
                    "indent_row": indent_row.to_dict(),
                    "rc_match_count": int(len(rc_matches)),
                    "tender_match_count": int(len(tender_matches)),
                    "po_match_count": int(len(po_matches)),
                    "po_candidate_qty": total_candidate_qty,
                    "po_allocated_qty": total_allocated_qty,
                    "po_pending_qty": po_pending_qty,
                    "po_review_candidates": po_reviews[["po_line_id", "po_no", "source_item_name", "ordered_qty", "location", "district", "match_score"]].to_dict(orient="records"),
                },
            )
        )

    allocation_rows.extend(
        _attach_package_components(mapping_rules.get("package_components", {}), po, allocation_rows, lifecycle_rows)
    )
    _suggest_generic_package_components(mapping_rules, po, allocation_rows, lifecycle_rows)

    lifecycle_rows.sort(key=lambda record: record.indent_line_id)
    return lifecycle_rows, allocation_rows


def _detect_excess_quantity(lifecycle_rows: List[LifecycleRecord]) -> List[Dict[str, Any]]:
    """Flag indent lines where the PO candidates offered more quantity than was
    required (I13 'Excess Quantity', P14 'Potential Over-Order'). Allocation
    already caps confirmed quantity at the required amount; this reports the
    excess that was left on the table instead of silently discarding it."""
    excesses: List[Dict[str, Any]] = []
    for record in lifecycle_rows:
        payload = record.raw_payload or {}
        required_qty = _to_float(record.required_qty)
        candidate_qty = _to_float(payload.get("po_candidate_qty"))
        allocated_qty = _to_float(payload.get("po_allocated_qty"))
        if required_qty <= 0 or allocated_qty < required_qty:
            continue
        excess_qty = candidate_qty - allocated_qty
        if excess_qty <= 0:
            continue
        excesses.append(
            {
                "batch_id": record.batch_id,
                "indent_line_id": record.indent_line_id,
                "source_item_name": record.source_item_name,
                "required_qty": required_qty,
                "candidate_qty": candidate_qty,
                "allocated_qty": allocated_qty,
                "excess_qty": excess_qty,
            }
        )
    return excesses


def _detect_duplicate_po_lines(database: ReconciliationDatabase) -> List[Dict[str, Any]]:
    """Identify exact duplicate PO rows (P12) - same PO number, item, quantity,
    amount AND facility all repeated - as distinct from legitimate repeated
    allocations of the same item across different facilities (P6)."""
    po = database.fetch_dataframe(
        "SELECT po_line_id, batch_id, po_no, source_file, source_sheet, source_item_name, "
        "ordered_qty, total_amount, location, district FROM po_lines"
    )
    if po.empty:
        return []
    po["item_key"] = po["source_item_name"].astype(str).map(normalize_lookup_key)
    po["qty_key"] = po["ordered_qty"].map(_to_float)
    po["amount_key"] = po["total_amount"].map(_to_float)
    po["facility_key"] = po["location"].map(_facility_key)
    po["district_key"] = po["district"].map(_district_key)

    duplicates: List[Dict[str, Any]] = []
    group_columns = ["po_no", "item_key", "qty_key", "amount_key", "facility_key", "district_key"]
    for _, group in po.groupby(group_columns):
        if len(group) <= 1 or not str(group["po_no"].iloc[0]).strip() or not group["item_key"].iloc[0]:
            continue
        duplicates.append(
            {
                "batch_id": group["batch_id"].iloc[0],
                "po_no": group["po_no"].iloc[0],
                "source_item_name": group["source_item_name"].iloc[0],
                "ordered_qty": group["qty_key"].iloc[0],
                "duplicate_count": int(len(group)),
                "po_line_ids": group["po_line_id"].astype(int).tolist(),
                "source_file": group["source_file"].iloc[0],
                "source_sheet": group["source_sheet"].iloc[0],
            }
        )
    return duplicates


def build_and_store_lifecycle(database: ReconciliationDatabase, mapping_rules: Dict[str, Any]) -> ReconciliationSummary:
    lifecycle_rows, allocation_rows = build_lifecycle_rows(database, mapping_rules)
    database.replace_reconciliation(lifecycle_rows, allocation_rows)

    # Data-quality and completeness exceptions are regenerated fresh on every
    # run so reruns stay idempotent instead of accumulating duplicates.
    connection = database.connect()
    connection.execute(
        "DELETE FROM exceptions WHERE exception_code IN ("
        "'PO_LINE_NOT_FOUND_IN_INDENT', 'PO_HEADER_AMOUNT_MISMATCH', "
        "'PO_QUANTITY_EXCEEDS_REQUIRED', 'DUPLICATE_PO_LINE')"
    )
    connection.commit()

    tolerance = float(mapping_rules.get("po_header_amount_tolerance", 1.0))
    for mismatch in _detect_po_header_amount_mismatches(database, tolerance):
        database.record_exception(
            batch_id=str(mismatch["batch_id"]),
            exception_code="PO_HEADER_AMOUNT_MISMATCH",
            severity="High",
            status="Open",
            summary=(
                f"PO {mismatch['po_no']}: header gross amount {mismatch['header_amount']:.2f} "
                f"does not match the sum of its own line amounts {mismatch['line_sum']:.2f}."
            ),
            details=mismatch,
        )

    for orphan in _detect_unmatched_po_lines(database, lifecycle_rows, allocation_rows):
        database.record_exception(
            batch_id=str(orphan["batch_id"]),
            exception_code="PO_LINE_NOT_FOUND_IN_INDENT",
            severity="Medium",
            status="Open",
            summary=(
                f"PO {orphan['po_no']} line '{orphan['source_item_name']}' (qty {orphan['ordered_qty']}) "
                f"at {orphan['location']}, {orphan['district']} has no corresponding line in the current indent."
            ),
            details=orphan,
            row_id=int(orphan["po_line_id"]),
        )

    for excess in _detect_excess_quantity(lifecycle_rows):
        database.record_exception(
            batch_id=str(excess["batch_id"]),
            exception_code="PO_QUANTITY_EXCEEDS_REQUIRED",
            severity="Medium",
            status="Open",
            summary=(
                f"Indent line '{excess['source_item_name']}' required {excess['required_qty']:g} but PO "
                f"candidates offered {excess['candidate_qty']:g} ({excess['excess_qty']:g} excess, "
                "Potential Over-Order)."
            ),
            details=excess,
            row_id=int(excess["indent_line_id"]),
        )

    for duplicate in _detect_duplicate_po_lines(database):
        database.record_exception(
            batch_id=str(duplicate["batch_id"]),
            exception_code="DUPLICATE_PO_LINE",
            severity="Medium",
            status="Open",
            summary=(
                f"PO {duplicate['po_no']} has {duplicate['duplicate_count']} identical lines for "
                f"'{duplicate['source_item_name']}' (qty {duplicate['ordered_qty']:g}) at the same facility."
            ),
            details=duplicate,
        )

    return ReconciliationSummary(lifecycle_rows=len(lifecycle_rows), allocation_rows=len(allocation_rows))
