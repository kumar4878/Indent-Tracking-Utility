from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^0-9A-Za-z]+")
WORD_TOKEN_RE = re.compile(r"[A-Za-z]+")


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def strip_html(value: Any) -> str:
    text = safe_text(value)
    text = html.unescape(text)
    text = HTML_TAG_RE.sub(" ", text)
    return text


def normalize_whitespace(value: Any) -> str:
    text = strip_html(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def normalize_lookup_key(value: Any) -> str:
    text = normalize_whitespace(value).lower()
    return NON_WORD_RE.sub("", text)


def normalize_header_text(value: Any) -> str:
    return normalize_whitespace(value)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    return normalize_whitespace(value) == ""


def extract_keyword_tokens(value: Any, stopwords: Optional[Set[str]] = None, min_length: int = 3) -> FrozenSet[str]:
    """Word-boundary-aware keyword tokens (lowercase alphabetic words only,
    numbers excluded since those are handled separately by numeric-spec
    guards). Generic/filler words (configurable via `stopwords`, e.g.
    "machine", "unit", "set") are dropped so two unrelated items that merely
    share a common noun do not appear to share a meaningful keyword. A simple
    plural heuristic (strip a trailing "s", but not "ss") folds "machines"/
    "monitors" onto "machine"/"monitor" so pluralization alone never hides or
    creates a shared keyword.
    """
    text = normalize_whitespace(value).lower()
    stopwords = stopwords or set()
    tokens = set()
    for token in WORD_TOKEN_RE.findall(text):
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        if len(token) >= min_length and token not in stopwords:
            tokens.add(token)
    return frozenset(tokens)


def extract_attribute_tags(value: Any, attribute_keyword_map: Optional[Dict[str, Dict[str, List[str]]]]) -> Dict[str, str]:
    """Scan text for critical-attribute hints (mobility, patient type, scale,
    operation, configuration, material, etc.) using a config-driven synonym
    map of {category: {canonical_tag: [synonym, ...]}}. Returns at most one
    canonical tag per category found in the text, via whole-word/phrase
    matching so short synonyms (e.g. "ss") cannot match inside unrelated
    words.
    """
    if not attribute_keyword_map:
        return {}
    text = f" {normalize_whitespace(value).lower()} "
    tags: Dict[str, str] = {}
    for category, canonical_map in attribute_keyword_map.items():
        for canonical, synonyms in canonical_map.items():
            for synonym in synonyms:
                pattern = r"\b" + re.escape(str(synonym).lower()) + r"\b"
                if re.search(pattern, text):
                    tags[category] = canonical
                    break
            if category in tags:
                break
    return tags


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, float) and value != value:
        return None
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(make_json_safe(value), ensure_ascii=True, default=str)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_payload(payload: Any) -> str:
    text = json_dumps(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
