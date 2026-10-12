from __future__ import annotations

from typing import Any, Dict, List

from cleaning_engine import normalize_lookup_key


def suggest_column_mapping(source_headers: List[str], source_type: str, mapping_rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    source_rules = mapping_rules.get(source_type, {})
    aliases = source_rules.get("aliases", {})
    mandatory = set(source_rules.get("mandatory", []))

    reverse_lookup: Dict[str, str] = {}
    for destination, alias_list in aliases.items():
        reverse_lookup[normalize_lookup_key(destination)] = destination
        for alias in alias_list:
            reverse_lookup[normalize_lookup_key(alias)] = destination

    suggestions: List[Dict[str, Any]] = []
    matched_destinations = set()
    for header in source_headers:
        destination = reverse_lookup.get(normalize_lookup_key(header), "")
        matched = bool(destination)
        if matched:
            matched_destinations.add(destination)
        suggestions.append(
            {
                "source_header": header,
                "destination_field": destination,
                "match_type": "alias" if matched else "unmapped",
                "confidence": 100 if matched else 0,
            }
        )

    missing_mandatory = sorted(item for item in mandatory if item not in matched_destinations)
    suggestions.append(
        {
            "source_header": "__mandatory_check__",
            "destination_field": ", ".join(missing_mandatory),
            "match_type": "missing_mandatory" if missing_mandatory else "complete",
            "confidence": 100 if not missing_mandatory else 0,
        }
    )
    return suggestions
