from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from cleaning_engine import is_blank, normalize_header_text, normalize_lookup_key
from models import HeaderDetectionResult


MAX_HEADER_PROBE_ROWS = 25


@dataclass(slots=True)
class RowScore:
    row_index: int
    score: float
    text_cells: int
    numeric_cells: int
    total_cells: int


def _row_text_cells(row: Sequence[Any]) -> Tuple[int, int, int]:
    text_cells = 0
    numeric_cells = 0
    meaningful = 0
    for value in row:
        if is_blank(value):
            continue
        meaningful += 1
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric_cells += 1
        else:
            text_cells += 1
    return text_cells, numeric_cells, meaningful


def score_header_row(row: Sequence[Any], row_index: int) -> RowScore:
    text_cells, numeric_cells, meaningful = _row_text_cells(row)
    score = text_cells * 2 + meaningful - numeric_cells * 2
    return RowScore(row_index=row_index, score=score, text_cells=text_cells, numeric_cells=numeric_cells, total_cells=meaningful)


def detect_header_row(rows: Sequence[Sequence[Any]], max_probe_rows: int = MAX_HEADER_PROBE_ROWS) -> HeaderDetectionResult:
    best_score: Optional[RowScore] = None
    best_row: Optional[Sequence[Any]] = None

    for row_index, row in enumerate(rows[:max_probe_rows]):
        candidate = score_header_row(row, row_index)
        if candidate.total_cells == 0:
            continue
        if best_score is None or candidate.score > best_score.score:
            best_score = candidate
            best_row = row

    if best_score is None or best_row is None:
        return HeaderDetectionResult(row_index=None, confidence=0.0, headers=[], notes="No usable header row detected")

    headers: List[str] = []
    for position, value in enumerate(best_row):
        if is_blank(value):
            headers.append(f"Column {position + 1}")
            continue
        headers.append(normalize_header_text(value))

    confidence = min(100.0, max(25.0, best_score.score * 10.0))
    note = f"Header row detected at zero-based index {best_score.row_index}"
    return HeaderDetectionResult(row_index=best_score.row_index, confidence=confidence, headers=headers, notes=note)
